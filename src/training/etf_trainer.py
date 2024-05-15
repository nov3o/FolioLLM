import torch
from accelerate.utils import HfDeepSpeedConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer, \
    DataCollatorForLanguageModeling, TrainerCallback
import logging

from accelerate import Accelerator

# Initialize the accelerator
accelerator = Accelerator(mixed_precision='fp16')  # Enable mixed precision

# Clear CUDA cache
torch.cuda.empty_cache()

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')


class MemoryMonitorCallback(TrainerCallback):
    def on_step_end(self, args, state, control, **kwargs):
        torch.cuda.empty_cache()
        print(f"GPU memory allocated: {torch.cuda.memory_allocated() / 1024**2:.2f} MB")
        print(f"GPU memory reserved: {torch.cuda.memory_reserved() / 1024**2:.2f} MB")

    def on_epoch_begin(self, args, state, control, **kwargs):
        torch.cuda.empty_cache()
        print("Cleared CUDA cache at the start of the epoch.")

class ETFTrainer:
    def __init__(self, model_name, etf_dataset):
        self.model_name = model_name
        self.etf_dataset = etf_dataset
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize_dataset(self):
        def tokenize_function(sample):
            try:
                # Convert the sample dictionary to a string representation
                input_text = f"ETF Ticker: {sample['etf_ticker']}\n"
                input_text += "Features:\n"
                for feature, value in sample['features'].items():
                    input_text += f"{feature}: {value}\n"

                # Tokenize the input text with padding and truncation
                model_inputs = self.tokenizer(
                    input_text,
                    padding='max_length',
                    truncation=True,
                    max_length=128  # Adjust max_length as needed
                )

                # Set the labels to be the same as the input IDs
                model_inputs["labels"] = model_inputs["input_ids"]

                return model_inputs
            except KeyError as e:
                logging.warning(f"Missing key '{e.args[0]}' in sample: {sample}")
                return None

        self.tokenized_dataset = self.etf_dataset.map(tokenize_function, batched=False, remove_columns=self.etf_dataset.column_names)
        self.tokenized_dataset = self.tokenized_dataset.filter(lambda x: x is not None)

    def train(self):
        data_collator = DataCollatorForLanguageModeling(tokenizer=self.tokenizer, mlm=False)  # Use mlm=False for causal LM

        # deepspeed_config = {
        #     "train_batch_size": "auto",  # Set to 'auto' to avoid mismatch errors
        #     "gradient_accumulation_steps": "auto",
        #     "fp16": {
        #         "enabled": True
        #     },
        #     "optimizer": {
        #         "type": "AdamW",
        #         "params": {
        #             "lr": 2e-5,
        #             "betas": [0.9, 0.999],
        #             "eps": 1e-8,
        #             "weight_decay": 0.01
        #         }
        #     },
        #     "zero_optimization": {
        #         "stage": 3,  # More aggressive memory optimization
        #         "offload_param": {
        #             "device": "cpu",  # Offload parameters to CPU
        #             "pin_memory": True
        #         },
        #         "offload_optimizer": {
        #             "device": "cpu",
        #             "pin_memory": True
        #         },
        #         "overlap_comm": True,  # Overlap communication with computation
        #         "contiguous_gradients": True,  # Use contiguous memory for gradients
        #         "reduce_bucket_size": 5e7,  # Adjust the bucket size for memory optimization
        #         "stage3_prefetch_bucket_size": 2e7,
        #         "stage3_param_persistence_threshold": 1e6,  # Threshold for param persistence in CPU
        #     },
        #     "aio": {
        #         "block_size": 1048576,  # 1 MB
        #         "queue_depth": 8,
        #         "thread_count": 1,
        #         "single_submit": False,
        #         "overlap_events": True,
        #     },
        # }

        deepspeed_config = {
            "train_batch_size": "auto",  # Set to 'auto' to avoid mismatch errors
            "gradient_accumulation_steps": "auto",
            "gradient_clipping": 1.0,
            "fp16": {
                "enabled": True
            },
            "zero_optimization": {
                "stage": 3,
                "offload_param": {
                    "device": "cpu",
                    "pin_memory": True
                },
                "offload_optimizer": {
                    "device": "cpu",
                    "pin_memory": True
                },
                "overlap_comm": True,
                "contiguous_gradients": True,
                "reduce_bucket_size": 5e7,
                "stage3_prefetch_bucket_size": 2e7,
                "stage3_param_persistence_threshold": 1e6,
            },
            "aio": {
                "block_size": 1048576,
                "queue_depth": 8,
                "thread_count": 1,
                "single_submit": False,
                "overlap_events": True,
            }
        }

        # Initialize DeepSpeed configuration
        ds_config = HfDeepSpeedConfig(deepspeed_config)

        training_args = TrainingArguments(
            output_dir='./results',
            evaluation_strategy='no',  # Disable evaluation during training for now
            learning_rate=2e-5,
            per_device_train_batch_size=8,#16,
            per_device_eval_batch_size=8,#64,
            num_train_epochs=3,
            weight_decay=0.01,
            gradient_accumulation_steps=16,
            logging_dir='./logs',
            fp16=True,
            deepspeed=ds_config.config,  # Use DeepSpeed for optimization

        )

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=self.tokenized_dataset,
            data_collator=data_collator,
        )

        trainer = accelerator.prepare(trainer)

        # Hook into training loop
        trainer.add_callback(MemoryMonitorCallback())

        trainer.train()

    def save_model(self, output_dir):
        self.model.save_pretrained(output_dir)
        self.tokenizer.save_pretrained(output_dir)

# Example usage
# etf_trainer = ETFTrainer("distilgpt2", your_etf_dataset)
# etf_trainer.tokenize_dataset()
# etf_trainer.train()
# etf_trainer.save_model("./output_model")
