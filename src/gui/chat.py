import random
import re
import torch
import gradio as gr
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.generation import TextStreamer

# Define the model name and the directory where the fine-tuned model is located
model_name = "FINGU-AI/FinguAI-Chat-v1"
output_dir = '../pipeline/fine_tuned_model/' + model_name

# Load the tokenizer and model from the fine-tuned directory
tokenizer = AutoTokenizer.from_pretrained(output_dir)
model = AutoModelForCausalLM.from_pretrained(output_dir)

# Set the device to GPU if available, otherwise CPU
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)


def optimization_prediction(user_input):
    # TODO: Improve
    return random.random()


def optim_generation(user_input, history):
    # TODO: Extract Tickers
    # TODO: add main_optimizer_mpt(tickers) call
    answer = "50% ABC\n25% CDE\n25DEF"
    # TODO: add Fingu reasoning (posterior explaination)
    history.append((user_input, answer))

respond = lambda inp, hist: raw_generation(inp, hist) if optimization_prediction(inp) > 0.5 else optim_generation(inp, hist)

def raw_generation(user_input, history):
    context = (
        "You are a financial specialist specializing in ETF portfolio construction and optimization. "
        "Your role is to assist users by providing accurate, timely, and insightful information to guide their investment decisions. "
        "Consider their risk tolerance, investment goals, and market conditions when offering advice."
    )
    messages = [
        {"role": "system", "content": context},
        {"role": "user", "content": user_input},
    ]
    # Tokenize the chat template
    tokenized_chat = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(device)

    # Define generation parameters
    generation_params = {
        'max_new_tokens': 1000,
        'use_cache': True,
        'do_sample': True,
        'temperature': 0.7,
        'top_p': 0.9,
        'top_k': 50,
        'eos_token_id': tokenizer.eos_token_id,
    }

    # Use a streamer for generating the response
    streamer = TextStreamer(tokenizer)

    # Generate the response
    outputs = model.generate(tokenized_chat, **generation_params, streamer=streamer)
    decoded_outputs = tokenizer.batch_decode(outputs)
    raw_answer = decoded_outputs[0]

    # Extract the assistant's response
    raw_answer = raw_answer.replace("<|im_end|>", "").replace("<|im_start|>", "")
    match = re.search(r"assistant\s*\n(.*?)(?=\nuser|\Z)", raw_answer, re.DOTALL)
    if match:
        answer = match.group(1).strip()
    else:
        answer = raw_answer.strip()

    # Append the new interaction to the history
    history.append((user_input, answer))
    return history


# Create the Gradio interface
with gr.Blocks() as demo:
    chatbot = gr.Chatbot(label="FolioLLM")
    with gr.Row():
        txt = gr.Textbox(show_label=False, placeholder="Type your message here...")  # Removed .style
        btn = gr.Button("Send")


    def submit_message(user_input, history=[]):
        new_history = respond(user_input, history)
        return new_history, ""


    btn.click(submit_message, [txt, chatbot], [chatbot, txt])

demo.launch()
