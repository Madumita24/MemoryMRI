# Day 2 Summary

- Git commit: `2d0943fb74079292bf8473931a19fd71494d2140`
- GPT model: `gpt-5.6`
- GPT score: `28/30`
- Deterministic score: `22/30`
- Deep dive case: `exp_09`

## Strongest Individual Replay

- `cs_01` on `cs_01_mem_2`: delta=1.0

## Strongest Pairwise Replay

- `cs_01` on `cs_01_mem_1, cs_01_mem_2`: combined=1.0, interaction=0.0, classification=dominated by one memory

## API Usage

- Total tokens: `89936`
- Approximate cost: `$0.7550`

## Known Limitations

- Pairwise and isolation evidence remain prompt-sensitive.
- Correct outcomes after ablation may still be unsupported by remaining evidence.
- Public API intentionally withholds benchmark answer-key fields.
