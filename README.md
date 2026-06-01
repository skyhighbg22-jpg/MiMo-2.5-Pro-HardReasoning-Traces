# Apex-Reasoning-Code-v1

A large-scale reasoning dataset of **4,713 expert-level prompts** across 32 academic and technical topics, generated using the `mimo-v2.5-pro` model. Each entry contains the full reasoning trace alongside the final completion, making it suitable for training and evaluating reasoning capabilities in language models.

## Dataset Statistics

| Metric | Value |
|---|---|
| Total entries | 4,713 |
| Total tokens | 27,104,198 |
| Prompt tokens | 1,771,339 |
| Completion tokens | 25,332,859 |
| Reasoning tokens | 16,542,264 |
| Unique topics | 32 |

## File Structure

```
apex_reasoning_dataset/
  manifest.json           # Dataset metadata and statistics
  reasoning_data_1.jsonl  # Entries 1-2000
  reasoning_data_2.jsonl  # Entries 2001-4000
  reasoning_data_3.jsonl  # Entries 4001-4713
generate_dataset.py       # Dataset generator script
test_api.py               # API connectivity test
test_concurrent.py        # Concurrency test
```

## Data Format

Each entry in the JSONL files contains:

```json
{
  "id": "uuid",
  "topic": "topic_category",
  "prompt": "the question or problem statement",
  "reasoning": "full step-by-step reasoning trace",
  "completion": "final answer or solution",
  "tokens": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "reasoning_tokens": 0
  },
  "timestamp": "ISO 8601 timestamp"
}
```

## Topics Covered (32 categories)

### Mathematics
- `matrix_eigenvalues_jordan` - Eigenvalues, eigenvectors, Jordan Canonical Form
- `calculus_lagrange_multipliers` - Multivariable optimization with constraints
- `ordinary_differential_equations` - Second-order ODEs with boundary conditions
- `linear_programming_simplex` - Linear programming via Simplex method
- `markov_stationary_distribution` - Markov chains and stationary distributions
- `diophantine_equations` - Linear Diophantine equations via Extended Euclidean Algorithm
- `chinese_remainder_theorem` - Systems of linear congruences
- `elliptic_curves` - Elliptic curves over finite fields
- `combinatorics_burnsides_lemma` - Burnside's Lemma and combinatorial counting
- `network_max_flow` - Ford-Fulkerson algorithm and min-cut

### Physics
- `quantum_harmonic_oscillator` - Quantum mechanics, ladder operators, uncertainty principle
- `relativity_and_astrophysics` - General relativity, cosmology, black holes
- `thermodynamics_and_statistical_mechanics` - Entropy, partition functions, phase transitions
- `particle_and_nuclear_physics` - QED, QCD, nuclear physics, Feynman diagrams

### Computer Science
- `algorithms_and_complexity` - NP-completeness, approximation algorithms, randomized algorithms
- `data_structures_and_databases` - B+ trees, LSM-trees, MVCC, CRDTs
- `distributed_systems_and_cloud` - Consensus protocols, CAP theorem, distributed storage
- `cryptography_and_security` - Zero-knowledge proofs, post-quantum crypto, side-channel attacks
- `compilers_and_programming_languages` - SSA, garbage collection, type systems
- `artificial_intelligence_and_ml` - Transformers, RLHF, diffusion models, GANs
- `operating_systems_and_networking` - TCP congestion control, virtual memory, scheduling
- `control_systems_and_information_theory` - Kalman filter, channel capacity, water-filling
- `distributed_system_architecture` - Large-scale system design (telemetry ingestion)

### Life Sciences
- `biochemistry_and_molecular_biology` - GPCRs, metabolic pathways, photosynthesis
- `genetics_and_bioinformatics` - Sequence alignment, GWAS, transposable elements
- `organic_and_physical_chemistry` - NMR spectroscopy, catalytic mechanisms, molecular orbitals

### Other
- `analytical_philosophy_and_epistemology` - Consciousness, free will, epistemology
- `game_theory_and_decision_theory` - Nash equilibria, mechanism design, auction theory
- `linguistics_and_formal_semantics` - Syntax, phonology, formal semantics
- `quantitative_finance_and_economics` - Black-Scholes, DSGE models, portfolio optimization
- `geometry_and_topology` - Gauss-Bonnet theorem, fundamental groups, homology

## Prompt Types

The dataset contains two types of prompts:

1. **Procedural** (~45%) - Dynamically generated problems with randomized parameters (matrices, capacities, coefficients, etc.). Each prompt is unique by construction.

2. **Theoretical** (~55%) - Template-based prompts with randomly selected sub-topics from a pool of ~400 advanced academic topics, with a random scaling parameter injected for uniqueness.

## Usage

### Load with Python

```python
import json

entries = []
for i in range(1, 4):
    with open(f"apex_reasoning_dataset/reasoning_data_{i}.jsonl", "r") as f:
        for line in f:
            entries.append(json.loads(line))

print(f"Loaded {len(entries)} entries")
```

### Load with Hugging Face Datasets

```python
from datasets import load_dataset

ds = load_dataset("skyhighbg22-jpg/Apex-Reasoning-Code-v1")
```

## Generation

The dataset was generated using `generate_dataset.py` with the following configuration:

- **Model**: `mimo-v2.5-pro`
- **Workers**: 10-15 concurrent threads (pipeline mode)
- **max_tokens**: 4096-16384
- **Temperature**: 0.7
- **Auto-retry**: Up to 10 retries with exponential backoff on 429/timeouts

To regenerate or extend the dataset:

```bash
python generate_dataset.py
```

Edit `ENTRY_TARGET` and `MAX_WORKERS` in the script to control the output size and parallelism.

## License

This dataset is provided as-is for research purposes.
