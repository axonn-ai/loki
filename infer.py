from transformers import AutoTokenizer, AutoModelForCausalLM
from axonn.models.transformers import parallelize 
from axonn import axonn as ax
import torch
import random
import numpy as np
import argparse
from datasets import load_dataset

from methods import init_tensor_saver
from methods.common.configure_model import get_h2o_args, get_topk_args, get_spar_args, get_pca_args, get_save_tensor_args
from methods.common.configure_model import get_modifier
from methods import init_logger, finish_logger
import methods

OKBLUE = '\033[94m'
OKGREEN = '\033[92m'
ENDC = '\033[0m'

def init_everything():
    torch.distributed.init_process_group(backend='nccl')
    world_size = torch.distributed.get_world_size()
    rank = torch.distributed.get_rank()
    if rank == 0:
        print(f"Going to distribute the model over {world_size} GPUs")
    ax.init(G_data=1, G_inter=1, G_intra_r=world_size, G_intra_c=1, G_intra_d=1)

def set_seed(seed=123456):
    # Extremely important for AxoNN
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", type=str, default="meta-llama/Llama-2-7b-hf", help="huggingface model to use")
    parser.add_argument("--method", type=str, default="baseline", choices=["baseline", "pca-topk"], help="method")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch Size")
    parser.add_argument("--prompt-length", type=int, default=1988, help="Batch Size")
    parser.add_argument("--gen-length", type=int, default=32, help="Batch Size")
    parser.add_argument("--seed", type=int, default=1234, help="Seed")
    parser.add_argument("--use-optimized-code", action='store_true', default=False)
    parser.add_argument("--warmup-iters", type=int, default=5)
    parser.add_argument("--total-iters", type=int, default=10)

    return parser

def load_prompts(tokenizer, batch_size, prompt_length):
    dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="test")
    encodings = tokenizer("\n\n".join(dataset["text"]), return_tensors="pt")
    total_tokens = encodings.input_ids.shape[1]
    input_ids = []
    for _ in range(batch_size):
        start_index = min(random.randint(0, total_tokens), total_tokens - prompt_length)
        tokens = encodings.input_ids[:, start_index : start_index + prompt_length].reshape(1, prompt_length)
        input_ids.append(tokens)
    input_ids = torch.cat(input_ids, dim=0)
    return input_ids

if  __name__ == "__main__":
    parser = setup_parser()
    args = parser.parse_args()
    model_id = args.model_id
    dtype = torch.float32

    init_everything()
    set_seed(args.seed)
   
    if args.method == "pca-topk":
        args.top_k = int(0.25 * args.prompt_length) 
        args.top_r = 16
        args.rotary_type = "postrotary"

        if args.use_optimized_code:
            from methods.pca_topk.modify_llama_optimized import make_llama_attention_pca_topk
        else:
            from methods.pca_topk.modify_llama import make_llama_attention_pca_topk

        make_llama_attention_pca_topk(args)

    if args.method == "baseline":
        from methods.pca_topk.modify_llama_hf_timers import make_llama_attention_hf_timers
        make_llama_attention_hf_timers(args)

    with parallelize(model_id):
        model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype).to('cuda')

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenized_prompts = load_prompts(tokenizer, args.batch_size, args.prompt_length)
    detokenized_prompts = tokenizer.batch_decode(tokenized_prompts) 

    total_generated_tokens = 0
    
    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)
    input_ids = tokenized_prompts.cuda() 
    
    # warmup iters
    for _ in range(args.warmup_iters):
        with torch.autocast(device_type='cuda', dtype=dtype):
            outputs = model.generate(input_ids, do_sample=True, max_new_tokens=args.gen_length)

    if torch.distributed.get_rank() == 0:
        if methods.G_TIMERS is not None:
            methods.G_TIMERS.get_times()

    # timed iters
    start_event.record()
    for _ in range(args.total_iters - args.warmup_iters):
        with torch.autocast(device_type='cuda', dtype=dtype):
            outputs = model.generate(input_ids, do_sample=True, max_new_tokens=args.gen_length)
            if torch.distributed.get_rank() == 0:
                if methods.G_TIMERS is not None:
                    print(methods.G_TIMERS.get_times(100))
    end_event.record()
    

    generated_tokens = outputs.numel() -  input_ids.numel()
    total_generated_tokens += generated_tokens
    
    torch.cuda.synchronize()
    total_time = start_event.elapsed_time(end_event) / (args.total_iters - args.warmup_iters)
    tput = total_generated_tokens * 1000 / total_time

    output_ids = outputs[:, args.prompt_length:]
    detokenized_generations = tokenizer.batch_decode(output_ids)

    if torch.distributed.get_rank() == 0:
        #for prompt, generation in zip(detokenized_prompts, detokenized_generations):
            #print(f"{OKBLUE}[PROMPT]: {prompt}{ENDC}")
            #print(f"{OKGREEN}[GENERATION]: = {generation}{ENDC}")
            #print("=====")
        print(f"Tput = {tput} generated tokens / second")


