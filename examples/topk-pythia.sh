#!/bin/bash

set -x
#sbatch examples/submit_topk.sh meta-llama/Llama-2-7b-hf llama 4096 0.125
#sbatch examples/submit_h2o.sh meta-llama/Llama-2-7b-hf llama 4096 0.25
#sbatch examples/submit_h2o.sh meta-llama/Llama-2-13b-hf llama 4096 0.125
#sbatch examples/submit_h2o.sh meta-llama/Llama-2-13b-hf llama 4096 0.25
#sbatch examples/submit_h2o.sh meta-llama/Llama-2-70b-hf llama 4096 0.125
#sbatch examples/submit_topk.sh meta-llama/Llama-2-70b-hf llama 4096 1024
#sbatch examples/submit_topk.sh meta-llama/Llama-2-70b-hf llama 4096 4096

#sbatch examples/submit_topk.sh mistralai/Mistral-7B-v0.1 mistral 4096 0.125 --lm-harness-eval
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 1 wikitext-test
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 0.25 wikitext-test
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 0.50 wikitext-test
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 1 wikitext-test --lm-harness-eval
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 0.25 wikitext-test --lm-harness-eval
sbatch examples/submit_topk.sh EleutherAI/pythia-6.9b gptneox 2048 0.50 wikitext-test --lm-harness-eval
set +x
