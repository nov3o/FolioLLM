import modal
from modal import Secret
import os

from src.pipeline.etf_pipeline import run_pipeline

# Create an image with the necessary dependencies from requirements.txt
image = modal.Image.debian_slim().pip_install_from_requirements("requirements.txt")

# Define the application with mounts and GPU requirements
output_volume = modal.Volume.from_name("fine_tuned_volume")

app = modal.App(
    "FolioLLM-pipeline",
    image=image,
    secrets=[Secret.from_name("my-huggingface-secret"), Secret.from_name("my-wandb-secret")],
    mounts=[
        modal.Mount.from_local_dir("data", remote_path="/root/data")
    ],
    volumes={
        "/root/fine_tuned_model/": output_volume,
    }
)


@app.function(gpu="A100", timeout=86400)  # Request a specific GPU type, e.g., A100, V100, etc.
def run():
    # Define the absolute path for the JSON file
    etf_data_palin_file = "/root/data/etf_data_v3_plain.json"
    test_prompts_file = "/root/data/basic-competency-test-prompts-1.json"
    training_prompts_template_file = "/root/data/training-template-adv.json"
    etf_data_cleaned_file = "/root/data/etf_data_v3_clean.json"
    portfolio_construction_q_prompts_file = "/root/data//portfolio_construction_q_prompts.json"

    # Ensure the W&B API key is set from the secret
    wandb_api_key = os.environ.get("WANDB_API_KEY")
    os.environ["WANDB_API_KEY"] = wandb_api_key

    run_pipeline(
        max_length=1024,
        eval_steps=500,
        learning_rate=2e-5,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        num_train_epochs=3,
        weight_decay=0.01,
        gradient_accumulation_steps=32,
        model_name='FINGU-AI/FinguAI-Chat-v1',
        json_structured_file=etf_data_palin_file,
        test_prompts_file=test_prompts_file,
        json_prompt_response_template_file=training_prompts_template_file,
        json_prompt_response_file_cleaned=etf_data_cleaned_file,
        portfolio_construction_q_prompts_file=portfolio_construction_q_prompts_file,
        output_dir="/root/fine_tuned_model/"
    )

@app.local_entrypoint()
def main():
    print("Run finetuning", run.remote())
