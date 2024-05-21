import torch
import wandb
from accelerate import Accelerator
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer, \
    DataCollatorForLanguageModeling, T5ForConditionalGeneration, T5Tokenizer
import logging
import json

from src.eval.etf_advisor_evaluator import ETFAdvisorEvaluator
from src.training.eval_at_start_callback import EvaluateAtStartCallback
from src.training.memory_monitor_callback import MemoryMonitorCallback
from src.training.wandb_callback import WandbCallback

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')


def tokenize_etf_text(trainer, sample, max_length=512):
    try:
        input_text = sample['text']

        model_inputs = trainer.tokenizer(
            input_text,
            padding='max_length',
            truncation=True,
            max_length=max_length  # 1024  # Adjust the max_length as needed
        )

        model_inputs["labels"] = model_inputs["input_ids"]

        return model_inputs
    except KeyError as e:
        logging.warning(f"Missing key '{e.args[0]}' in sample: {sample}")
        return None


def tokenize_structured_json(trainer, sample, max_length=256):
    try:
        input_text = f"ETF Ticker: {sample['etf_ticker']}\n"
        input_text += "Features:\n"
        for feature, value in sample['features'].items():
            input_text += f"{feature}: {value}\n"

        model_inputs = trainer.tokenizer(
            input_text,
            padding='max_length',
            truncation=True,
            max_length=max_length  # 1024  # Adjust the max_length as needed
        )

        model_inputs["labels"] = model_inputs["input_ids"]

        return model_inputs
    except KeyError as e:
        logging.warning(f"Missing key '{e.args[0]}' in sample: {sample}")
        return None


def tokenize_prompt_response(trainer, sample, max_length=256):
    try:
        prompt_inputs = trainer.tokenizer(
            sample['prompt'],
            padding='max_length',
            truncation=True,
            max_length=max_length  # Adjusted for combined length
        )
        response_inputs = trainer.tokenizer(
            sample['response'],
            padding='max_length',
            truncation=True,
            max_length=max_length
        )

        model_inputs = {
            'input_ids': prompt_inputs['input_ids'] + response_inputs['input_ids'][1:],
            'attention_mask': prompt_inputs['attention_mask'] + response_inputs['attention_mask'][1:]
        }

        model_inputs["labels"] = model_inputs["input_ids"].copy()

        return model_inputs
    except KeyError as e:
        logging.warning(f"Missing key '{e.args[0]}' in sample: {sample}")
        return None


class ETFTrainer:
    def __init__(self, model_name, etf_dataset, tokenize_function, test_prompts, max_length=512):
        self.model_name = model_name
        self.etf_dataset = etf_dataset
        self.tokenize_function = tokenize_function
        self.test_prompts = test_prompts

        if "t5" in self.model_name.lower():
            self.tokenizer = T5Tokenizer.from_pretrained(self.model_name)
            self.model = T5ForConditionalGeneration.from_pretrained(self.model_name)
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(self.model_name)

        # Set tokenizer padding side to 'left'
        self.tokenizer.padding_side = 'left'

        # Set pad_token to eos_token if not already set
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.accelerator = Accelerator()
        self.model, self.tokenizer = self.accelerator.prepare(self.model, self.tokenizer)
        self.model = self.model.to(self.accelerator.device)

        # Enable gradient checkpointing
        self.model.gradient_checkpointing_enable()

        self.max_length = max_length

    def tokenize_dataset(self):
        def tokenize_function(sample):
            return self.tokenize_function(self, sample, self.max_length)

        self.tokenized_dataset = self.etf_dataset.map(tokenize_function, batched=False,
                                                      remove_columns=self.etf_dataset.column_names)
        self.tokenized_dataset = self.tokenized_dataset.filter(lambda x: x is not None)

    def train(self):
        data_collator = DataCollatorForLanguageModeling(tokenizer=self.tokenizer,
                                                        mlm=False)  # Use mlm=False for causal LM

        deepspeed_config_path = {
            "train_batch_size": "auto",
            "gradient_accumulation_steps": "auto",
            "gradient_clipping": 1.0,
            "fp16": {
                "enabled": "auto"
            },
            "zero_optimization": {
                "stage": 3,
                "offload_param": {
                    "device": "cpu",
                    "pin_memory": "true"
                },
                "offload_optimizer": {
                    "device": "cpu",
                    "pin_memory": "true"
                },
                "overlap_comm": "true",
                "contiguous_gradients": "true",
                "reduce_bucket_size": 50000000,
                "stage3_prefetch_bucket_size": "20000000",
                "stage3_param_persistence_threshold": 1000000
            },
            "aio": {
                "block_size": 1048576,
                "queue_depth": 8,
                "thread_count": 1,
                "single_submit": "false",
                "overlap_events": "true"
            }
        }

        training_args = TrainingArguments(
            output_dir='./results',
            evaluation_strategy='steps',  # Change to 'steps' to enable evaluation during training
            eval_steps=20,  # Adjust frequency of evaluation
            #evaluation_strategy='epoch',
            learning_rate=2e-5,
            per_device_train_batch_size=1,  # Adjusted for memory constraints
            per_device_eval_batch_size=1,  # Adjusted for memory constraints
            num_train_epochs=5,
            weight_decay=0.01,
            gradient_accumulation_steps=64,
            logging_dir='./logs',
            fp16=True,
            deepspeed=deepspeed_config_path,  # Use DeepSpeed for optimization
            logging_steps=1,  # Log the training loss every # steps
        )

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=self.tokenized_dataset,
            eval_dataset=self.tokenized_dataset,
            # Using the same dataset for simplicity, ideally use a separate validation set
            data_collator=data_collator,
            compute_metrics=self.compute_metrics
        )

        # Hook into training loop
        # trainer.add_callback(MemoryMonitorCallback())

        trainer.add_callback(WandbCallback())
        trainer.add_callback(EvaluateAtStartCallback())

        trainer.train()


    def compute_metrics(self, eval_pred):
        evaluator = ETFAdvisorEvaluator(self.model, self.tokenizer, self.test_prompts)
        eval_results = evaluator.evaluate(detailed=False)
        wandb.log(eval_results)  # Log evaluation results to wandb
        return eval_results


    def save_model(self, output_dir):
        self.model.save_pretrained(output_dir)
        self.tokenizer.save_pretrained(output_dir)

# Example usage
# etf_trainer = ETFTrainer("distilgpt2", your_etf_dataset, tokenize_structured_json)
# etf_trainer.tokenize_dataset()
# etf_trainer.train()
# etf_trainer.save_model("./output_model")
