import os
import json
import uuid
import time
import ssl
import random
import sys
import atexit
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

# API Configurations
API_URL = "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"
API_KEY = "tp-sou9oupysvtbeqkup8w4gmofoes888teci3waykpy1cqc8un"
MODEL_NAME = "mimo-v2.5-pro"
TOKEN_LIMIT = 567_000_000

# Parallelism Configurations
MAX_WORKERS = 15
BATCH_SIZE = 15
RATE_LIMIT_DELAY = 2

# Entry Target (set to 0 to use TOKEN_LIMIT instead)
ENTRY_TARGET = 7278

# Output Paths
DATASET_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(DATASET_DIR, "manifest.json")
LOCK_PATH = os.path.join(DATASET_DIR, ".generator.lock")

ssl_context = ssl._create_unverified_context()

# Thread-safety primitives
manifest_lock = threading.Lock()
file_write_lock = threading.Lock()
print_lock = threading.Lock()


# ---------------------------------------------------------
# Process Lock — prevents duplicate generators
# ---------------------------------------------------------
def acquire_lock():
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH, "r") as f:
                lock_data = json.load(f)
            existing_pid = lock_data.get("pid")
            if existing_pid and is_process_running(existing_pid):
                print(f"FATAL: Another generator is already running (PID {existing_pid}).")
                print(f"Kill it first, or delete {LOCK_PATH}")
                sys.exit(1)
            else:
                tlog(f"Stale lock found (PID {existing_pid} dead). Removing.")
                os.remove(LOCK_PATH)
        except Exception:
            os.remove(LOCK_PATH)

    lock_data = {"pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}
    with open(LOCK_PATH, "w") as f:
        json.dump(lock_data, f)
    atexit.register(release_lock)


def release_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass


def is_process_running(pid):
    try:
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, subprocess.SubprocessError):
        return False


def tlog(msg):
    with print_lock:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------
# PROCEDURAL HARD PROBLEM GENERATORS
# ---------------------------------------------------------
def gen_matrix_problem():
    dim = random.choice([3, 4])
    matrix = [[random.randint(-5, 10) for _ in range(dim)] for _ in range(dim)]
    matrix_str = "\n".join(["[" + ", ".join(map(str, row)) + "]" for row in matrix])
    problem = (
        f"Consider the following {dim}x{dim} matrix A:\n{matrix_str}\n\n"
        f"Perform a rigorous step-by-step linear algebraic derivation to:\n"
        f"1. Find the characteristic polynomial p(λ) of the matrix.\n"
        f"2. Calculate all eigenvalues (including complex ones if they exist) and their algebraic multiplicities.\n"
        f"3. Find the basis for the eigenspace of each eigenvalue (geometric multiplicities).\n"
        f"4. Determine if the matrix is diagonalizable. If it is defective, derive its generalized eigenvectors and construct the full Jordan Canonical Form J and the transition matrix P such that A = P * J * P^-1.\n"
        f"Show every calculation and step in detail."
    )
    return "matrix_eigenvalues_jordan", problem

def gen_crt_problem():
    m1, m2, m3 = random.sample([3, 5, 7, 11, 13, 17], 3)
    a1 = random.randint(1, m1 - 1)
    a2 = random.randint(1, m2 - 1)
    a3 = random.randint(1, m3 - 1)
    problem = (
        f"Solve the following system of linear congruences simultaneously using the Chinese Remainder Theorem:\n"
        f"x ≡ {a1} (mod {m1})\n"
        f"x ≡ {a2} (mod {m2})\n"
        f"x ≡ {a3} (mod {m3})\n\n"
        f"Verify each step, calculate the modular multiplicative inverses carefully, and prove the uniqueness of the solution modulo {m1 * m2 * m3}."
    )
    return "chinese_remainder_theorem", problem

def gen_diophantine_problem():
    import math
    a = random.randint(10, 150)
    b = random.randint(10, 150)
    c = random.randint(5, 50)
    g = math.gcd(a, b)
    if random.choice([True, False]):
        c = c * g
    problem = (
        f"Analyze and solve the linear Diophantine equation:\n"
        f"{a}x + {b}y = {c}\n\n"
        f"1. Determine whether a solution exists by calculating the Greatest Common Divisor (GCD) using the Extended Euclidean Algorithm.\n"
        f"2. If solutions exist, find a specific initial solution (x0, y0) using back-substitution.\n"
        f"3. Formulate the general solution parameters for x and y in terms of integer parameter t.\n"
        f"4. If no solution exists, prove mathematically why no such integer coordinates can satisfy the relation."
    )
    return "diophantine_equations", problem

def gen_elliptic_curve_problem():
    p = random.choice([11, 13, 17, 19, 23, 29])
    a = random.randint(1, 5)
    b = random.randint(1, 5)
    problem = (
        f"Consider the elliptic curve E defined over the finite field F_{p} by the Weierstrass equation:\n"
        f"y^2 ≡ x^3 + {a}x + {b} (mod {p})\n\n"
        f"1. Verify if the curve is non-singular by calculating the discriminant Δ = -16(4a^3 + 27b^2) (mod {p}).\n"
        f"2. List all the points (x, y) belonging to E(F_{p}), including the point at infinity.\n"
        f"3. Pick a non-trivial point P from your generated list and calculate 2P (point doubling) and 3P using the elliptic curve addition formulas.\n"
        f"4. State the order of the group E(F_{p}) and confirm if it satisfies Hasse's theorem bound."
    )
    return "elliptic_curves", problem

def gen_graph_flow_problem():
    capacities = {
        "S->A": random.randint(10, 20),
        "S->B": random.randint(10, 20),
        "A->B": random.randint(2, 8),
        "A->T": random.randint(8, 15),
        "B->T": random.randint(10, 18)
    }
    problem = (
        f"Consider a network flow graph with Source node S and Sink node T. The directed edges and their respective capacities are:\n"
        f"- S -> A: capacity = {capacities['S->A']}\n"
        f"- S -> B: capacity = {capacities['S->B']}\n"
        f"- A -> B: capacity = {capacities['A->B']}\n"
        f"- A -> T: capacity = {capacities['A->T']}\n"
        f"- B -> T: capacity = {capacities['B->T']}\n\n"
        f"Apply the Ford-Fulkerson or Dinic's algorithm to:\n"
        f"1. Find the maximum possible flow from S to T step-by-step.\n"
        f"2. Illustrate each augmenting path, its bottleneck capacity, and the residual graph updates at each stage.\n"
        f"3. Find the corresponding minimum-capacity cut in the network. List the partition sets of vertices U and V, and verify that the max-flow equals the min-cut capacity."
    )
    return "network_max_flow", problem

def gen_markov_chain_problem():
    p11 = round(random.uniform(0.1, 0.4), 2)
    p12 = round(random.uniform(0.1, 0.4), 2)
    p13 = round(1.0 - p11 - p12, 2)
    p21 = round(random.uniform(0.1, 0.4), 2)
    p22 = round(random.uniform(0.1, 0.4), 2)
    p23 = round(1.0 - p21 - p22, 2)
    p31 = round(random.uniform(0.1, 0.4), 2)
    p32 = round(random.uniform(0.1, 0.4), 2)
    p33 = round(1.0 - p31 - p32, 2)
    problem = (
        f"A discrete-time Markov chain has three states: S = {{1, 2, 3}}. The transition probability matrix P is given by:\n"
        f"P = [\n"
        f"  [{p11:.2f}, {p12:.2f}, {p13:.2f}],\n"
        f"  [{p21:.2f}, {p22:.2f}, {p23:.2f}],\n"
        f"  [{p31:.2f}, {p32:.2f}, {p33:.2f}]\n"
        f"]\n\n"
        f"1. Verify that P is a valid stochastic matrix.\n"
        f"2. Prove whether this Markov chain is irreducible and aperiodic.\n"
        f"3. Formulate the system of linear equations π * P = π and Σ π_i = 1, and solve for the stationary probability vector π = [π_1, π_2, π_3] using detailed algebraic derivations.\n"
        f"4. Calculate the mean recurrence times for each state."
    )
    return "markov_stationary_distribution", problem

def gen_linear_programming_problem():
    c1 = random.randint(10, 50)
    c2 = random.randint(10, 50)
    a11, a12 = random.randint(2, 6), random.randint(2, 6)
    b1 = random.randint(20, 60)
    a21, a22 = random.randint(1, 5), random.randint(2, 8)
    b2 = random.randint(15, 50)
    problem = (
        f"Optimize the following linear programming problem using the Simplex method or graphical analysis (providing full analytical derivations):\n"
        f"Maximize Objective Function: Z = {c1}x1 + {c2}x2\n\n"
        f"Subject to the constraints:\n"
        f"1) {a11}x1 + {a12}x2 ≤ {b1}\n"
        f"2) {a21}x1 + {a22}x2 ≤ {b2}\n"
        f"and non-negativity constraints x1 ≥ 0, x2 ≥ 0.\n\n"
        f"1. Standardize the LP model by introducing slack variables s1 and s2.\n"
        f"2. Build the initial Simplex tableau.\n"
        f"3. Perform the pivoting steps, identify the entering and leaving variables at each iteration, and explain your choices.\n"
        f"4. Find the optimal coordinates (x1*, x2*) and the maximum value of Z. Derive the dual of this LP problem and state its optimal solution."
    )
    return "linear_programming_simplex", problem

def gen_calculus_extremum_problem():
    coeff = random.randint(2, 6)
    c = random.randint(100, 500)
    problem = (
        f"Find the extreme values of the multi-variable function:\n"
        f"f(x, y, z) = x^2 + y^2 + z^2\n\n"
        f"subject to the non-linear constraint equations:\n"
        f"g1(x, y, z) = x + y + z - 12 = 0\n"
        f"g2(x, y, z) = x^2 + {coeff}y^2 - z = {c}\n\n"
        f"1. Construct the Lagrangian function L(x, y, z, λ1, λ2) using multiple Lagrange multipliers.\n"
        f"2. Set up the system of partial derivatives with respect to x, y, z, λ1, λ2 to find all critical points.\n"
        f"3. Solve this non-linear system algebraically, showing all intermediate reductions.\n"
        f"4. Evaluate the bordered Hessian matrix to classify each critical point as a local minimum, local maximum, or saddle point."
    )
    return "calculus_lagrange_multipliers", problem

def gen_differential_equation_problem():
    a = random.choice([2, 3, 4])
    b = random.randint(5, 15)
    problem = (
        f"Solve the following non-homogeneous second-order ordinary differential equation with boundary conditions:\n"
        f"y'' + {a}y' + {b}y = e^(-2x) * cos(3x)\n"
        f"Initial conditions: y(0) = 1, y'(0) = 0\n\n"
        f"1. Find the general solution of the corresponding homogeneous equation y_h(x) using the characteristic equation method.\n"
        f"2. Find the particular solution y_p(x) using either the Method of Undetermined Coefficients or the Variation of Parameters. Show all integration and algebraic steps in full detail.\n"
        f"3. Combine both parts and apply the boundary conditions to determine the exact constants of the solution.\n"
        f"4. Discuss the physical behavior of this system (e.g. damping class, resonance effects)."
    )
    return "ordinary_differential_equations", problem

def gen_combinatorics_counting_problem():
    n = random.randint(8, 15)
    r = random.randint(3, n-3)
    problem = (
        f"Consider a circular table with {n} distinct seats. We want to place {r} identical red tokens and {n-r} identical blue tokens on these seats such that:\n"
        f"1. No two red tokens are in adjacent seats.\n"
        f"2. We account for rotational symmetries (i.e. rotations of the table are considered equivalent, but reflections are distinct).\n\n"
        f"Perform a rigorous combinatorics derivation using:\n"
        f"1. Burnside's Lemma (the Orbit-Stabilizer Theorem) to count the number of distinct configurations under rotational symmetry.\n"
        f"2. Formulate the generating function of placing red and blue tokens with the specified adjacency constraint.\n"
        f"3. Calculate the exact numerical count of valid non-equivalent configurations for the case where n = {n} and r = {r}. Explain every partition logic step."
    )
    return "combinatorics_burnsides_lemma", problem

def gen_physics_problem():
    m = random.randint(10, 100)
    omega = random.randint(1, 5)
    problem = (
        f"A quantum particle of mass m = {m} kg resides in a 1D harmonic oscillator potential V(x) = 0.5 * m * ω^2 * x^2 with ω = {omega} rad/s.\n"
        f"1. Write down the time-independent Schrödinger equation for this system.\n"
        f"2. Using the ladder operator method (creation a† and annihilation a operators), derive the quantized energy eigenvalues E_n.\n"
        f"3. Find the normalized ground-state wave function ψ0(x) by solving the first-order differential equation a * ψ0(x) = 0.\n"
        f"4. Calculate the expectation values <x>, <p>, <x^2>, <p^2>, and verify Heisenberg's Uncertainty Principle Δx * Δp for the ground state ψ0(x) and the first excited state ψ1(x) explicitly."
    )
    return "quantum_harmonic_oscillator", problem

def gen_system_architecture_scenario():
    req_sec = random.choice([500000, 1000000, 2000000])
    latency_ms = random.choice([20, 50, 100])
    regions = random.randint(3, 5)
    problem = (
        f"Architect a globally distributed real-time telemetry ingestion system capable of handling {req_sec:,} write requests per second.\n"
        f"System Requirements and Constraints:\n"
        f"- P99 Ingestion Latency: < {latency_ms}ms\n"
        f"- Deployment: {regions} geographical regions globally\n"
        f"- Durability: Zero data loss guarantee (RPO=0) even in the event of an entire regional datacenter failure\n"
        f"- Query pattern: High write volume, with real-time map-reduce analytical jobs running concurrently over sliding 5-minute windows.\n\n"
        f"Provide an expert-level system design breakdown addressing:\n"
        f"1. The network ingestion layer (DNS, Global Load Balancing, Anycast routing, API gateway strategies).\n"
        f"2. The message broker and buffering architecture (partitioning, offset management, replication topology across regions).\n"
        f"3. The storage engine choice (NoSQL, LSM-tree databases, columnar structures) and replication consensus configurations (Raft, Multi-Paxos vs asynchronous replication patterns).\n"
        f"4. State management, consistency model trade-offs (CAP/PACELC theorem analysis), and how you guarantee durability without violating the latency budget."
    )
    return "distributed_system_architecture", problem


THEORETICAL_TOPICS = [
    "geometry_and_topology", "relativity_and_astrophysics", "thermodynamics_and_statistical_mechanics",
    "particle_and_nuclear_physics", "organic_and_physical_chemistry", "biochemistry_and_molecular_biology",
    "genetics_and_bioinformatics", "algorithms_and_complexity", "data_structures_and_databases",
    "distributed_systems_and_cloud", "cryptography_and_security", "compilers_and_programming_languages",
    "artificial_intelligence_and_ml", "operating_systems_and_networking", "formal_logic_and_set_theory",
    "analytical_philosophy_and_epistemology", "game_theory_and_decision_theory", "linguistics_and_formal_semantics",
    "quantitative_finance_and_economics", "control_systems_and_information_theory"
]

SUB_TOPICS = {
    "geometry_and_topology": [
        "proving the Gauss-Bonnet theorem for compact surfaces with boundary",
        "calculating fundamental groups of topological spaces using the Seifert-van Kampen theorem",
        "proving the classification of compact 2-manifolds step-by-step",
        "calculating simplicial homology groups for complex triangulated spaces",
        "explaining the Poincare conjecture and the role of Ricci flow with surgery",
        "deriving curvature tensors (Riemann, Ricci, Weyl) on pseudo-Riemannian manifolds",
        "proving the Brouwer Fixed Point Theorem using differential forms and Stokes' theorem",
        "analyzing geodesics on general surfaces of revolution using Euler-Lagrange equations",
        "calculating the Euler characteristic of complex algebraic varieties",
        "explaining de Rham cohomology and proving de Rham's theorem",
        "analyzing connections on vector bundles and deriving Yang-Mills equations",
        "proving properties of Hausdorff spaces and Urysohn's Lemma",
        "deriving the metric tensor for hyperbolic space and analyzing its isometry group",
        "explaining symplectic manifolds and Hamiltonian mechanics formulation",
        "calculating the intersection numbers of homology classes on algebraic surfaces",
        "proving the Morse index theorem for critical points of energy functionals",
        "analyzing knot invariants and calculating the Jones polynomial of complex knots",
        "explaining covering spaces and their classification by fundamental group subgroups",
        "deriving the exterior derivative operations on differential k-forms",
        "analyzing minimal surfaces and solving Plateau's problem",
        "explaining algebraic topology concepts of cobordism and characteristic classes"
    ],
    "relativity_and_astrophysics": [
        "deriving the Schwarzschild metric from Einstein's field equations in vacuum",
        "calculating geodesic orbits of photons and massive particles around a black hole",
        "deriving the Friedmann equations from the FLRW metric in cosmology",
        "calculating cosmic inflation parameters and scalar spectral index relations",
        "modeling stellar structure and nucleosynthesis reactions using Lane-Emden equation",
        "deriving gravitational wave emission from binary pulsar systems in quadrupole approximation",
        "calculating the temperature and emission spectrum of Hawking radiation from black holes",
        "explaining gravitational lensing equations and calculating Einstein ring radii",
        "deriving the Tolman-Oppenheimer-Volkoff (TOV) equation for hydrostatic equilibrium of neutron stars",
        "explaining cosmic microwave background (CMB) anisotropies and acoustic peaks",
        "deriving the Lorentz transformation equations from Einstein's postulates",
        "calculating the perihelion precession of Mercury using general relativity corrections",
        "explaining the Penrose process and energy extraction from rotating Kerr black holes",
        "modeling the accretion disk structure around active galactic nuclei (AGN)",
        "deriving the Chandrasekhar limit for white dwarf stars using degenerate electron pressure",
        "explaining dark matter profiles (NFW, isothermal) and rotation curve anomalies",
        "analyzing gravitational collapse and the formation of apparent horizons",
        "deriving the red-shift formula in expanding cosmological spacetimes",
        "explaining the Sachs-Wolfe effect on CMB photon propagation",
        "modeling the evolution of cosmological perturbations during the radiation era",
        "analyzing cosmic strings and other topological defects in the early universe"
    ],
    "thermodynamics_and_statistical_mechanics": [
        "calculating entropy changes in non-equilibrium thermodynamic cycles with irreversibilities",
        "deriving all Maxwell relations from thermodynamic potentials via exact differentials",
        "analyzing phase transitions and chemical potentials using the Clausius-Clapeyron equation",
        "solving heat transport differential equations under complex Dirichlet and Neumann boundaries",
        "deriving the partition function for the 2D Ising model using transfer matrices",
        "calculating Fermi-Dirac and Bose-Einstein distribution functions from grand canonical ensembles",
        "deriving the equations of state for a van der Waals gas from intermolecular potentials",
        "analyzing the thermodynamics of black holes (laws, temperature, entropy limits)",
        "calculating transport coefficients (viscosity, thermal conductivity) from the Boltzmann equation",
        "deriving the fluctuation-dissipation theorem in linear response theory",
        "solving the master equation for simple stochastic processes in thermal baths",
        "calculating the critical exponents of continuous phase transitions using renormalization group",
        "deriving Landau's theory of phase transitions and identifying order parameters",
        "analyzing the thermodynamics of superconducting transitions using Ginzburg-Landau theory",
        "calculating the partition function of a 1D diatomic gas with rotational and vibrational degrees",
        "explaining the Gibbs paradox and resolving it via quantum indistinguishability",
        "deriving Onsager reciprocal relations from microscopic reversibility",
        "calculating thermodynamic properties of degenerate electron gases in metals",
        "modeling Bose-Einstein condensation temperatures and condensate fractions in harmonic traps",
        "deriving the Debye and Einstein models for heat capacity of solids",
        "analyzing the work extraction bounds under quantum thermodynamic constraints"
    ],
    "particle_and_nuclear_physics": [
        "deriving the semi-empirical mass formula (Bethe-Weizsäcker) and fitting parameters",
        "calculating nuclear binding energies and analyzing nuclear shell model configurations",
        "deriving decay rates and selection rules for beta decay using Fermi theory",
        "calculating the cross section of Rutherford scattering using quantum scattering theory",
        "explaining the Higgs mechanism and spontaneous symmetry breaking in the Standard Model",
        "deriving Feynman rules for quantum electrodynamics (QED) from the Lagrangian",
        "calculating the muon decay rate and lifetime using electroweak coupling metrics",
        "explaining quark confinement and asymptotic freedom in Quantum Chromodynamics (QCD)",
        "deriving the Gell-Mann-Nishijima formula and analyzing hadron SU(3) flavor representations",
        "calculating neutrino oscillation probabilities in vacuum and matter (MSW effect)",
        "explaining CP violation in the neutral kaon system and the CKM matrix parameters",
        "deriving Breit-Wigner resonance shapes for unstable particle cross sections",
        "analyzing deep inelastic scattering to deduce nucleon parton distribution functions",
        "explaining the mechanism of nucleosynthesis (r-process, s-process) in stars",
        "calculating fusion reaction rates in tokamak reactors under thermonuclear conditions",
        "deriving the equations for radioactive decay chains (Bateman equations)",
        "explaining the nuclear force in terms of meson exchange (Yukawa potential)",
        "analyzing anomalous magnetic moments (g-2) of leptons in QED loops",
        "deriving the conservation laws associated with Noether's theorem in field theory",
        "explaining the experimental signatures of Quark-Gluon Plasma (QGP) in heavy-ion collisions",
        "calculating the decay width of the Z boson into quarks and leptons"
    ],
    "organic_and_physical_chemistry": [
        "predicting stereochemical outcomes of multi-step organic synthesis pathways",
        "proposing detailed curved-arrow mechanisms for electrophilic aromatic substitution",
        "analyzing molecular orbital correlation diagrams for electrocyclic reactions (Woodward-Hoffmann)",
        "interpreting 1D and 2D NMR spectra (COSY, HSQC) to deduce molecular structure",
        "deriving the rate laws for complex catalytic mechanisms (Michaelis-Menten, Langmuir-Hinshelwood)",
        "calculating activation energies and pre-exponential factors using the Eyring equation",
        "explaining the quantum mechanical origin of chemical bonding using molecular orbital theory",
        "analyzing the vibrational modes of molecules using infrared spectroscopy and group theory",
        "deriving the thermodynamic parameters of electrochemical cells using the Nernst equation",
        "proposing synthetic routes for highly functionalized natural products containing chiral centers",
        "explaining the mechanism of Pd-catalyzed cross-coupling reactions (Suzuki, Heck, Negishi)",
        "calculating molecular geometries and dipole moments using Huckel Molecular Orbital theory",
        "analyzing photochemical transitions and constructing Jablonski diagrams",
        "explaining the hydrophobic effect in thermodynamics of protein folding",
        "deriving the Debye-Hückel theory of electrolyte solutions and activity coefficients",
        "proposing mechanisms for radical polymerization and calculating kinetic chain lengths",
        "analyzing acid-base equilibria in non-aqueous solvents and calculating pH values",
        "explaining the physical basis of surface plasmon resonance in gold nanoparticles",
        "deriving the adsorption isotherms (Langmuir, BET) from statistical mechanics",
        "analyzing the transition state structures of SN2 reactions using computational metrics",
        "proposing total synthesis plans for molecules containing complex bridged ring systems"
    ],
    "biochemistry_and_molecular_biology": [
        "explaining transcriptional regulation of the lac operon under glucose and lactose gradients",
        "designing CRISPR-Cas9 guide RNAs and outlining detailed off-target risk mitigations",
        "explaining signal transduction pathways leading to cytochrome c release in apoptosis",
        "modeling gene regulatory networks using non-linear differential equations",
        "deriving the Michaelis-Menten equation under steady-state assumptions with competitive inhibitors",
        "explaining the molecular mechanism of ATP synthesis by F1F0-ATP synthase",
        "analyzing the thermodynamic stability of DNA double helices and calculating melting profiles",
        "proposing the structural basis of protein folding using Ramachandran plots",
        "explaining the catalytic mechanism of serine proteases (chymotrypsin) in detail",
        "modeling metabolic pathways and calculating flux balances using optimization methods",
        "explaining the mechanism of eukaryotic DNA replication and telomere maintenance",
        "analyzing post-translational modifications (phosphorylation, ubiquitination) and their signaling outcomes",
        "designing a recombinant protein purification protocol using affinity and size-exclusion chromatography",
        "explaining the molecular basis of muscle contraction via the sliding filament theory",
        "analyzing membrane transport kinetics of ion channels using the Goldman-Hodgkin-Katz equation",
        "explaining the lipid bilayer phase transitions and the effect of cholesterol",
        "modeling the kinetics of ligand-receptor binding with cooperative allosteric interactions",
        "explaining the biochemical pathways of photosynthesis (light reactions and Calvin cycle)",
        "analyzing the structure and function of GPCRs (G-protein coupled receptors) and G-protein activation",
        "proposing mechanisms of RNA splicing and spliceosome assembly step-by-step",
        "explaining the protein translation initiation pathway in eukaryotes and translation regulation"
    ],
    "genetics_and_bioinformatics": [
        "designing a dynamic programming algorithm for global sequence alignment (Needleman-Wunsch)",
        "implementing Burrows-Wheeler Transform (BWT) and FM-index for ultra-fast read mapping",
        "constructing phylogenetic trees from distance matrices using Neighbor-Joining algorithms",
        "modeling population genetics using the Hardy-Weinberg equilibrium with selection pressure",
        "designing a genome-wide association study (GWAS) and calculating statistical significance thresholds",
        "explaining genetic linkage and calculating recombination frequencies from multi-point crosses",
        "modeling the propagation of mutations in asexual populations using branching processes",
        "designing algorithms for de novo genome assembly using de Bruijn graph structures",
        "analyzing RNA-seq differential expression data using negative binomial models",
        "explaining epigenetic inheritance mechanisms (DNA methylation, histone modifications)",
        "modeling genetic drift using the Wright-Fisher model and diffusion equations",
        "designing hidden Markov models (HMM) for gene prediction and exon-intron boundary detection",
        "analyzing metagenomic sequencing data to classify microbial taxonomic profiles",
        "explaining the molecular mechanism of genomic imprinting and its evolutionary origins",
        "designing algorithms for structural variant detection from long-read sequencing data",
        "modeling gene duplication and divergence pathways using mathematical models",
        "analyzing single-cell RNA-seq clustering using dimensionality reduction (t-SNE, UMAP)",
        "explaining the genetics of quantitative traits and estimating herizability indices",
        "designing synthetic gene circuits for logical operations (AND, OR gates) in Escherichia coli",
        "analyzing protein-protein interaction networks and calculating network centrality metrics",
        "modeling the population dynamics of transposable elements under host silencing mechanisms"
    ],
    "algorithms_and_complexity": [
        "designing optimal dynamic programming algorithms for sequence alignment with affine gap penalties",
        "analyzing time and space complexity of advanced self-balancing search trees (AVL, Red-Black)",
        "implementing segment trees or Fenwick trees for dynamic range query optimization",
        "designing and proving approximation bounds of algorithms for the NP-hard Traveling Salesperson",
        "proving NP-completeness of the 3-SAT problem using reduction techniques",
        "designing randomized algorithms (Quicksort, Karger's Min-Cut) and analyzing expected runtimes",
        "analyzing the complexity of matrix multiplication and proving upper bounds of Strassen's algorithm",
        "designing online algorithms (caching, paging) and calculating their competitive ratios",
        "solving network flow problems using the push-relabel algorithm and analyzing complexity bounds",
        "designing streaming algorithms (HyperLogLog, Count-Min Sketch) for cardinallity estimation",
        "proving lower bounds for comparison-based sorting algorithms and searching problems",
        "designing parameterized algorithms for vertex cover and proving kernelization properties",
        "explaining quantum algorithms (Shor's, Grover's) and analyzing their speedups",
        "designing parallel algorithms for prefix sums and analyzing work-depth models",
        "proving properties of amortized analysis (accounting, potential methods) on dynamic structures",
        "designing geometric algorithms (convex hull, closest pair of points) and analyzing runtimes",
        "analyzing the complexity of linear programming and comparing simplex and interior-point methods",
        "proving the Cook-Levin theorem showing that Satisfiability is NP-complete",
        "designing approximation algorithms for Knapsack and Bin Packing problems",
        "analyzing tree decomposition and computing tree-width of complex graphs",
        "designing cache-oblivious algorithms for matrix multiplication and transposition"
    ],
    "data_structures_and_databases": [
        "optimizing B+ tree indexing structures for range query performance on disk storage",
        "designing lock-free concurrent data structures (queues, stacks) using compare-and-swap (CAS)",
        "analyzing database transaction isolation levels (Read Committed, Serializable) and concurrency anomalies",
        "implementing Log-Structured Merge-trees (LSM-trees) and optimizing compaction algorithms",
        "designing persistent data structures that preserve historical versions after modifications",
        "optimizing SQL query execution plans using cost-based optimizers and index statistics",
        "designing distributed database partitioning strategies (sharding) using consistent hashing",
        "implementing multi-version concurrency control (MVCC) in transactional database engines",
        "designing conflict-free replicated data types (CRDTs) for collaborative document editing",
        "optimizing garbage collection algorithms in high-throughput database systems",
        "designing write-ahead logging (WAL) protocols and analyzing crash recovery mechanisms (ARIES)",
        "implementing cache replacement policies (LRU, LFU, ARC) and analyzing hit-rate performance",
        "designing external memory sorting algorithms for datasets larger than main memory",
        "optimizing spatial database indexing using R-trees and quad-trees",
        "designing high-performance inverted indexes for full-text search engines",
        "implementing Bloom filters and cuckoo filters and calculating false positive rates",
        "analyzing database replication protocols (synchronous vs asynchronous) and consensus",
        "designing column-oriented storage formats for analytical database systems",
        "implementing lock-based concurrency control protocols (2PL, Strict 2PL)",
        "designing a distributed lock manager using consensus backends",
        "optimizing memory-mapped files (mmap) for high-performance key-value databases"
    ],
    "distributed_systems_and_cloud": [
        "explaining consensus protocols in Raft under network partitions and node failures",
        "analyzing consistency models in distributed databases under the CAP theorem bounds",
        "designing globally distributed task scheduling architectures with state durability",
        "explaining vector clocks and conflict-free replicated data types (CRDTs) for synchronization",
        "designing a scalable distributed storage system resembling Google File System (GFS)",
        "architecting an active-active multi-region deployment with zero data loss recovery objectives",
        "explaining Paxos consensus protocol invariants and multi-paxos optimizations",
        "designing a high-throughput event streaming platform like Apache Kafka",
        "architecting a secure distributed rate limiter handling millions of requests per second",
        "explaining Paxos vs Raft consensus performance profiles and architectural choices",
        "designing a distributed transactions system using 2-Phase Commit (2PC) and Saga patterns",
        "architecting an API gateway with dynamic routing, circuit breaking, and load balancing",
        "explaining MapReduce programming model internals and fault tolerance mechanisms",
        "designing distributed tracing systems (Dapper) to profile microservices pipelines",
        "architecting resilient auto-scaling systems on public cloud infrastructure",
        "explaining gossip protocols for cluster membership and failure detection (SWIM)",
        "designing a serverless container orchestration platform with cold-start mitigations",
        "architecting low-latency stateful WebSocket server groups with horizontal scalability",
        "explaining CAP theorem extensions (PACELC) and their practical implications",
        "designing secure multi-tenant network isolation layers in cloud environments",
        "architecting a distributed CDN with edge computing capabilities and global state sync"
    ],
    "cryptography_and_security": [
        "analyzing cryptographic weaknesses in custom elliptic curve schemes and timing attacks",
        "explaining zero-knowledge proofs (zk-SNARKs) and proposing a step-by-step verification scheme",
        "proving security bounds of symmetric cipher block modes (CBC, GCM)",
        "designing secure multi-party computation protocols for private voting systems",
        "analyzing vulnerabilities in modern authentication protocols (OAuth2, SAML)",
        "designing homomorphic encryption schemes for private outsourcing of computations",
        "explaining post-quantum cryptography algorithms (lattice-based, Kyber, Dilithium)",
        "proving the security of the Diffie-Hellman key exchange under the DDH assumption",
        "designing a secure enclave-based (SGX) execution pipeline for sensitive data",
        "analyzing buffer overflow vulnerabilities and mitigating them using ASLR, DEP, and canaries",
        "explaining side-channel analysis (differential power analysis) and mitigation techniques",
        "designing cryptographically secure pseudo-random number generators (CSPRNG)",
        "proving collision resistance properties of modern cryptographic hash functions",
        "designing secure public key infrastructure (PKI) with certificate revocation lists",
        "analyzing man-in-the-middle (MITM) attacks on TLS handshake protocols",
        "explaining zero-trust security architectures and access control models (ABAC, RBAC)",
        "designing secure firmware update mechanisms with hardware root of trust",
        "analyzing the security of multi-signature wallet contracts on public ledgers",
        "explaining the mechanics of format string vulnerabilities and automated detection",
        "designing end-to-end encrypted messaging systems with forward secrecy (Double Ratchet)",
        "analyzing the security implications of quantum computers on RSA and ECC schemes"
    ],
    "compilers_and_programming_languages": [
        "designing a lexical analyzer and parser for custom programming languages using LL(k) grammars",
        "implementing static single assignment (SSA) form and related compiler optimizations",
        "designing garbage collection algorithms (generational, mark-sweep, reference counting) step-by-step",
        "explaining type inference systems (Hindley-Milner) and implementing a prototype",
        "designing an efficient virtual machine interpreter with a JIT compiler pipeline",
        "analyzing programming language memory models and concurrent data-race guarantees",
        "implementing data-flow analysis frameworks for dead code elimination and constant folding",
        "designing algebraic data types (ADTs) and pattern-matching compilers",
        "explaining macro systems (hygienic macros) and AST transformation pipelines",
        "designing type safety proofs for simple typed lambda calculus",
        "implementing register allocation algorithms using graph coloring techniques",
        "designing a source-to-source compiler (transpiler) preserving source maps",
        "explaining dynamic dispatch, vtables, and devirtualization optimizations",
        "designing formal operational and denotational semantics for imperative loops",
        "implementing copy-on-write (COW) and value semantics in custom compilers",
        "designing a linting tool with abstract syntax tree (AST) static analysis rules",
        "explaining memory safety mechanisms in systems languages (borrow checker, ownership)",
        "designing intermediate representations (IR) optimized for vectorization",
        "implementing tail-call optimization (TCO) in recursive execution environments",
        "designing a gradual typing system with runtime contract checking",
        "explaining the structural vs nominal type equivalence systems and their trade-offs"
    ],
    "artificial_intelligence_and_ml": [
        "deriving backpropagation equations for convolutional layers with arbitrary strides and padding",
        "explaining the mathematical motivation of Self-Attention and multi-head attention",
        "designing reinforcement learning algorithms (Q-learning, PPO) for continuous control",
        "analyzing bias-variance tradeoffs and regularizations (L1, L2, Dropout) from basic principles",
        "deriving updates for variational autoencoders (VAE) and the evidence lower bound (ELOB)",
        "explaining generative adversarial networks (GANs) and analyzing mode collapse solutions",
        "designing gradient descent optimization algorithms (Adam, RMSprop) from scratch",
        "analyzing the convergence guarantees of stochastic gradient descent (SGD) on non-convex manifolds",
        "deriving the loss formulation for diffusion models and explaining the reverse process",
        "explaining transformer model scaling laws and computational bottlenecks (FLOPs/token)",
        "designing neural architecture search (NAS) strategies using reinforcement learning",
        "deriving structural proofs of universal approximation theorems for neural networks",
        "explaining sequence-to-sequence models with attention and decoding strategies (beam search)",
        "designing anomaly detection pipelines using isolation forests and autoencoders",
        "explaining graph neural networks (GNN) and message passing architectures",
        "deriving support vector machine (SVM) dual formulations and kernel functions",
        "analyzing contrastive representation learning paradigms (SimCLR, CLIP)",
        "explaining the mechanical interpretability of neural network weights (induction heads)",
        "designing reinforcement learning from human feedback (RLHF) training loops",
        "deriving maximum entropy reinforcement learning frameworks (Soft Actor-Critic)",
        "explaining model quantization techniques (INT8, FP4) and post-training calibration"
    ],
    "operating_systems_and_networking": [
        "designing preemptive CPU scheduling algorithms (multi-level feedback queue) for low latency",
        "architecting virtual memory paging systems and implementing page replacement algorithms",
        "analyzing TCP congestion control algorithms (Cubic, BBR) and packet loss recovery",
        "designing low-latency network I/O multiplexing systems using epoll or kqueue",
        "architecting file system directory trees and optimizing inode allocation on disk",
        "explaining process synchronization primitives (mutexes, semaphores, condvars) and deadlock detection",
        "designing container virtualization layers using Linux namespaces and cgroups",
        "architecting real-time operating system (RTOS) schedulers with priority inheritance",
        "explaining modern network routing protocols (BGP, OSPF) and convergence analysis",
        "designing virtual private network (VPN) protocols with cryptographic packet encapsulation",
        "explaining DNS resolution paths and designing highly available geo-DNS routing",
        "designing custom network protocols over UDP with reliability and ordering guarantees",
        "architecting highly resilient network topologies with spanning tree protocols (STP)"
    ],
    "formal_logic_and_set_theory": [
        "proving completeness and soundness of propositional logic using semantic tableaux",
        "evaluating modal logic systems (S4, S5) using Kripke relational semantics",
        "explaining Gödel's First and Second Incompleteness Theorems and their proofs",
        "deriving proofs in first-order predicate logic with nested quantifiers",
        "proving the Cantor-Bernstein-Schroeder theorem in axiomatic set theory",
        "explaining the axiom of choice, Zorn's lemma, and the well-ordering theorem",
        "proving independence results in set theory using the forcing method",
        "explaining transfinite induction and calculating ordinal arithmetic limits",
        "deriving completeness results for first-order logic (Gödel's completeness theorem)",
        "explaining the Löwenheim-Skolem theorem and its philosophical implications",
        "proving properties of intuitionistic logic and the Brouwer-Heyting-Kolmogorov semantics",
        "explaining the curry-howard isomorphism and its application to proof assistants",
        "proving the undecidability of the halting problem using diagonal arguments",
        "explaining non-standard analysis and the construction of hyperreal numbers",
        "deriving proofs in temporal logic for model checking of systems",
        "explaining Russell's paradox and the transition to Zermelo-Fraenkel set theory",
        "proving the independence of the continuum hypothesis from ZFC",
        "explaining paraconsistent logics and the handling of logical contradictions",
        "deriving theorems in lambda calculus and proving the Church-Rosser theorem",
        "explaining many-valued logics and their applications in engineering systems",
        "proving the compact theorem for propositional and first-order logic"
    ],
    "analytical_philosophy_and_epistemology": [
        "deconstructing Newcomb's paradox and evaluating decision theory outcomes",
        "analyzing the hard problem of consciousness under functionalist paradigms",
        "evaluating Searle's Chinese Room argument and computational theory of mind",
        "deconstructing Nozick's tracking theory of knowledge against Gettier counterexamples",
        "evaluating Putnam's Brain in a Vat argument and semantic externalism",
        "deconstructing Quine's two dogmas of empiricism and the analytic-synthetic distinction",
        "evaluating Kripke's Naming and Necessity and the theory of rigid designators",
        "analyzing McTaggart's argument on the unreality of time (A-series vs B-series)",
        "deconstructing Goodman's new riddle of induction and the grue-bleen paradox",
        "evaluating the Ship of Theseus paradox and theories of personal identity",
        "analyzing free will and determinism under compatibilist and incompatibilist views",
        "deconstructing Strawson's reactive attitudes and moral responsibility",
        "evaluating Bostrom's simulation argument and its probabilistic formulations",
        "analyzing Sellars' myth of the given and foundationalism in epistemology",
        "deconstructing Davidson's anomalous monism and the philosophy of action",
        "evaluating the Sorites paradox and theories of vagueness in logic",
        "analyzing the ethics of belief under Clifford's evidentialism",
        "deconstructing Nagel's 'What is it like to be a bat?' and physicalism",
        "evaluating Lewis' modal realism and the existence of possible worlds",
        "analyzing external world skepticism and G.E. Moore's dogmatic response",
        "deconstructing Dummett's anti-realism and the rejection of the law of excluded middle"
    ],
    "game_theory_and_decision_theory": [
        "finding mixed-strategy Nash equilibria in asymmetric multi-player games",
        "deriving subgame perfect equilibria in sequential bargaining games",
        "analyzing mechanism design and defining incentive compatibility rules",
        "solving cooperative games using the Shapley value calculation",
        "explaining evolutionary game theory and evolutionary stable strategies (ESS)",
        "deriving the minimax theorem for zero-sum games from duality theory",
        "analyzing double auction mechanisms and calculating equilibrium strategies",
        "explaining the traveler's dilemma and rationalizability in game theory",
        "solving sequential games of incomplete information using perfect Bayesian equilibria",
        "explaining Arrow's Impossibility Theorem and proving it step-by-step",
        "analyzing Vickrey-Clarke-Groves (VCG) mechanisms and proving truthfulness",
        "solving the centipede game using backward induction and analyzing deviations",
        "explaining the tragedy of the commons and designing regulatory incentives",
        "analyzing matching markets and proving the core properties of housing markets",
        "solving signal games and distinguishing pooling and separating equilibria",
        "explaining Savage's foundation of subjective utility and decision axioms",
        "analyzing voting systems (Borda count, instant runoff) and strategic manipulation",
        "solving infinite horizon repeated games using trigger strategies",
        "explaining prospect theory and deviations from expected utility theory",
        "analyzing public goods games and calculating voluntary contribution limits",
        "solving the principal-agent problem under moral hazard and adverse selection"
    ],
    "linguistics_and_formal_semantics": [
        "analyzing syntactic tree structures of complex nested structural ambiguity",
        "explaining Montague semantics and formalizing natural language sentences",
        "analyzing conversational implicatures under Grice's maxims",
        "modeling semantic shifts in historical linguistics using computational frameworks",
        "explaining Chomsky's hierarchy of formal grammars and their recognition complexity",
        "deriving semantic representations of quantified noun phrases using lambda calculus",
        "analyzing structural case marking systems (ergative-absolutive vs nominative-accusative)",
        "explaining the phonological rules of assimilation and lenition in generative phonology",
        "analyzing pragmatics and speech act theory (locutionary, illocutionary, perlocutionary)",
        "modeling language acquisition pathways using statistical learning frameworks",
        "explaining the Whorfian hypothesis (linguistic relativity) and cognitive linguistics proofs",
        "analyzing binding theory (Principles A, B, C) in generative syntax",
        "deriving truth conditions of conditional sentences using possible-world semantics",
        "explaining the minimal list program in modern generative grammar",
        "analyzing morphological typology (agglutinative, polysynthetic, isolating languages)",
        "modeling discourse representation structures (DRT) for anaphora resolution",
        "explaining the linguistic basis of politeness theory (face-saving acts)",
        "analyzing lexical semantics and lexical relations (hyponymy, polysemy)",
        "deriving optimality theory constraint hierarchies for phonological patterns",
        "explaining the structure of creole languages and pidgin evolution pathways",
        "analyzing the syntactic parameters of head-directionality across languages"
    ],
    "quantitative_finance_and_economics": [
        "deriving the Black-Scholes-Merton differential equation from arbitrage-free portfolios",
        "calculating option pricing under stochastic volatility models (Heston model)",
        "analyzing portfolio optimization using Markowitz mean-variance efficiency frontiers",
        "deriving the Capital Asset Pricing Model (CAPM) from market equilibrium assumptions",
        "modeling interest rate dynamics using the Vasicek and Cox-Ingersoll-Ross (CIR) frameworks",
        "calculating Value at Risk (VaR) and Expected Shortfall under fat-tailed distributions",
        "analyzing dynamic stochastic general equilibrium (DSGE) models in macroeconomics",
        "deriving the Modigliani-Miller theorem under perfect capital market assumptions",
        "modeling business cycles using real business cycle (RBC) models",
        "analyzing optimal monetary policy rules (Taylor rule) in New Keynesian economics",
        "deriving the Black-Litterman model starting from Markowitz optimization",
        "calculating credit risk probabilities using structural models (Merton model)",
        "analyzing market microstructure and bid-ask spread models (Roll model)",
        "deriving the arbitrage pricing theory (APT) as an alternative to CAPM",
        "modeling high-frequency order book dynamics using Hawkes processes",
        "analyzing structural vector autoregression (SVAR) models in macroeconometrics",
        "deriving the Lucas critique and its impact on macroeconomic policy design",
        "calculating optimal execution strategies using Almgren-Chriss models",
        "analyzing game-theoretic models of oligopolistic competition (Cournot, Bertrand)",
        "modeling asset price bubbles using rational bubble models",
        "deriving the Solow-Swan growth model and analyzing steady-state paths"
    ],
    "control_systems_and_information_theory": [
        "calculating Shannon entropy and channel capacity for noisy communication channels",
        "deriving Kalman filter equations for state estimation of linear dynamical systems",
        "analyzing stability of non-linear control systems using Lyapunov's direct method",
        "designing optimal control policies using the Linear Quadratic Regulator (LQR)",
        "proving the Nyquist-Shannon sampling theorem and analyzing aliasing distortion",
        "designing PID controllers and analyzing frequency response parameters (Bode plots)",
        "deriving the capacity of MIMO (multiple-input multiple-output) wireless systems",
        "analyzing controllability and observability matrices of state-space systems",
        "designing state-feedback controllers using pole placement techniques",
        "explaining error-correcting codes (Reed-Solomon, LDPC) and decoding boundaries",
        "deriving the rate-distortion function in lossy data compression frameworks",
        "analyzing adaptive control systems using model reference adaptive control (MRAC)",
        "designing sliding mode controllers for robust stabilization of uncertain systems",
        "explaining the Kullback-Leibler divergence and its applications in statistical physics",
        "deriving the Hamilton-Jacobi-Bellman (HJB) equation in continuous-time optimal control",
        "analyzing stability of discrete-time systems using the Jury stability criterion",
        "explaining polar codes and their capacity-achieving properties in modern networking",
        "designing robust controllers using H-infinity optimization methods",
        "deriving the differential entropy of continuous multivariate normal distributions",
        "analyzing the water-filling algorithm for optimal power allocation across channels",
        "designing model predictive control (MPC) frameworks under state constraints"
    ]
}

PROMPT_TEMPLATES = [
    "Analyze and solve this challenging problem in detail: {sub_topic}. Focus on a rigorous mathematical or technical walkthrough. Think step by step and present your full logical reasoning trace before giving the final solution.",
    "Draft a comprehensive, highly technical analysis of {sub_topic}. Include a thorough mathematical or structural breakdown, investigate edge cases, explain your internal model and assumptions, and formulate the exact reasoning trace.",
    "Formulate a complete proof or systemic design for the following topic: {sub_topic}. Provide a step-by-step logical derivation of every lemma, axiom, or engineering trade-off. Show all intermediate steps and detail your thinking process clearly.",
    "Deconstruct {sub_topic} down to its fundamental principles. Propose a complex scenario or concrete math puzzle within this area, then solve it rigorously. Make sure to detail your internal reasoning, corrections, and logical flow.",
    "Provide an expert-level, detailed tutorial solving {sub_topic}. Frame a difficult, non-trivial hypothetical problem first, then detail the step-by-step mathematical or architectural reasoning to resolve it."
]

PROCEDURAL_GENERATORS = [
    gen_matrix_problem,
    gen_crt_problem,
    gen_diophantine_problem,
    gen_elliptic_curve_problem,
    gen_graph_flow_problem,
    gen_markov_chain_problem,
    gen_linear_programming_problem,
    gen_calculus_extremum_problem,
    gen_differential_equation_problem,
    gen_combinatorics_counting_problem,
    gen_physics_problem,
    gen_system_architecture_scenario,
]


def generate_dynamic_prompt():
    if random.random() < 0.45:
        generator = random.choice(PROCEDURAL_GENERATORS)
        topic, prompt = generator()
        return topic, prompt
    else:
        topic = random.choice(THEORETICAL_TOPICS)
        sub_topic = random.choice(SUB_TOPICS[topic])
        template = random.choice(PROMPT_TEMPLATES)
        prompt = template.format(sub_topic=sub_topic)
        random_id = random.randint(100000, 999999)
        prompt += f"\n\nNote: For your analysis, assume a system dimension/scale context defined by the parameter index base-k where k = {random_id}. Explain how this specific configuration changes your quantitative outcomes."
        return topic, prompt


# ---------------------------------------------------------
# Manifest & JSONL Operations (thread-safe)
# ---------------------------------------------------------
def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            tlog(f"Error reading manifest: {e}. Reinitializing...")
    return {
        "dataset_name": "Apex-Reasoning-Code-v1",
        "version": "1.0.0",
        "total_files": 0,
        "total_entries": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "files_generated": [],
        "topics_covered": []
    }


def save_manifest(manifest):
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    if os.path.exists(MANIFEST_PATH):
        os.remove(MANIFEST_PATH)
    os.rename(tmp, MANIFEST_PATH)


def get_output_file_path():
    with manifest_lock:
        manifest = load_manifest()
        if not manifest["files_generated"]:
            new_file = "reasoning_data_1.jsonl"
            manifest["files_generated"].append(new_file)
            manifest["total_files"] = 1
            save_manifest(manifest)
            return os.path.join(DATASET_DIR, new_file)

        current_file = manifest["files_generated"][-1]
        current_path = os.path.join(DATASET_DIR, current_file)

    line_count = 0
    if os.path.exists(current_path):
        try:
            with open(current_path, "r", encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
        except Exception:
            pass

    if line_count >= 2000:
        with manifest_lock:
            manifest = load_manifest()
            new_index = len(manifest["files_generated"]) + 1
            new_file = f"reasoning_data_{new_index}.jsonl"
            manifest["files_generated"].append(new_file)
            manifest["total_files"] = len(manifest["files_generated"])
            save_manifest(manifest)
            return os.path.join(DATASET_DIR, new_file)

    return current_path


def append_record(record):
    file_path = get_output_file_path()
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with file_write_lock:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)


def update_manifest(topic, p_tokens, c_tokens, t_tokens, r_tokens):
    with manifest_lock:
        manifest = load_manifest()
        manifest["total_entries"] += 1
        manifest["total_tokens"] += t_tokens
        manifest["prompt_tokens"] += p_tokens
        manifest["completion_tokens"] += c_tokens
        manifest["reasoning_tokens"] += r_tokens
        if topic not in manifest["topics_covered"]:
            manifest["topics_covered"].append(topic)
        save_manifest(manifest)
        return manifest["total_entries"], manifest["total_tokens"]


# ---------------------------------------------------------
# API Requester with Exponential Backoff
# ---------------------------------------------------------
def make_api_request(prompt, max_retries=10):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096
    }
    req_body = json.dumps(data).encode("utf-8")

    for attempt in range(max_retries):
        req = urllib.request.Request(API_URL, data=req_body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ssl_context, timeout=600) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                wait = min(2 ** (attempt + 2), 120)
                tlog(f"  429 rate limited — backing off {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            elif e.code >= 500:
                wait = min(5 * (attempt + 1), 60)
                tlog(f"  HTTP {e.code} — retrying in {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as e:
            wait = min(5 * (attempt + 1), 60)
            tlog(f"  Network error — retrying in {wait}s (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(wait)

    raise RuntimeError(f"API request failed after {max_retries} retries")


# ---------------------------------------------------------
# Single Entry Worker (called by thread pool)
# ---------------------------------------------------------
def generate_single_entry(entry_num):
    topic, prompt = generate_dynamic_prompt()
    tlog(f"[Worker] #{entry_num} Topic={topic} — sending request...")

    start = time.time()
    response = make_api_request(prompt)
    duration = time.time() - start

    choice = response["choices"][0]
    message = choice["message"]
    content = message.get("content", "")
    reasoning = message.get("reasoning_content", "")

    usage = response.get("usage", {})
    p_tokens = usage.get("prompt_tokens", 0)
    c_tokens = usage.get("completion_tokens", 0)
    t_tokens = usage.get("total_tokens", 0)
    r_tokens = 0
    if "completion_tokens_details" in usage:
        r_tokens = usage["completion_tokens_details"].get("reasoning_tokens", 0)
    elif "reasoning_tokens" in usage:
        r_tokens = usage["reasoning_tokens"]

    if t_tokens == 0:
        p_tokens = len(prompt) // 4
        c_tokens = len(content) // 4
        r_tokens = len(reasoning) // 4
        t_tokens = p_tokens + c_tokens

    record = {
        "id": str(uuid.uuid4()),
        "topic": topic,
        "prompt": prompt,
        "reasoning": reasoning,
        "completion": content,
        "tokens": {
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": t_tokens,
            "reasoning_tokens": r_tokens
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    append_record(record)
    total_entries, total_tokens = update_manifest(topic, p_tokens, c_tokens, t_tokens, r_tokens)

    tlog(f"[Done]  #{entry_num} {topic} in {duration:.1f}s | tokens={t_tokens:,} (reasoning={r_tokens:,}) | cumulative={total_tokens:,} ({total_tokens/TOKEN_LIMIT*100:.4f}%)")

    return {
        "entry_num": entry_num,
        "topic": topic,
        "tokens": t_tokens,
        "total_tokens": total_tokens,
        "duration": duration
    }


# ---------------------------------------------------------
# Main — Continuous Pipeline (no batch stalls)
# ---------------------------------------------------------
def main():
    acquire_lock()

    print("=" * 60)
    print("APEX REASONING DATASET GENERATOR (PIPELINE)")
    print(f"Target Token Limit: {TOKEN_LIMIT:,}")
    if ENTRY_TARGET > 0:
        print(f"Entry Target: {ENTRY_TARGET:,}")
    print(f"Target Model: {MODEL_NAME}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60, flush=True)

    manifest = load_manifest()
    print(f"Loaded manifest. Existing entries: {manifest['total_entries']:,}, Total tokens: {manifest['total_tokens']:,}", flush=True)

    if ENTRY_TARGET > 0 and manifest["total_entries"] >= ENTRY_TARGET:
        print(f"Entry target {ENTRY_TARGET:,} already reached! Exiting.", flush=True)
        return
    if manifest["total_tokens"] >= TOKEN_LIMIT:
        print("Target token limit already reached! Exiting.", flush=True)
        return

    entry_counter = manifest["total_entries"]
    shutdown = False

    def signal_handler(sig, frame):
        nonlocal shutdown
        print("\n[!] Shutdown requested. Finishing in-flight workers...", flush=True)
        shutdown = True

    import signal
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    active_futures = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="gen") as executor:
        for _ in range(MAX_WORKERS):
            entry_counter += 1
            f = executor.submit(generate_single_entry, entry_counter)
            active_futures[f] = entry_counter

        while not shutdown and active_futures:
            done, _ = wait(active_futures, return_when=FIRST_COMPLETED)

            for f in done:
                eid = active_futures.pop(f)
                try:
                    f.result()
                except Exception as exc:
                    tlog(f"[FAIL] Entry #{eid} raised: {exc}")

            manifest = load_manifest()
            if ENTRY_TARGET > 0 and manifest["total_entries"] >= ENTRY_TARGET:
                print(f"\nEntry target reached! {manifest['total_entries']:,} entries.", flush=True)
                break
            if manifest["total_tokens"] >= TOKEN_LIMIT:
                print(f"\nToken target reached! {manifest['total_tokens']:,} tokens.", flush=True)
                break

            for _ in range(len(done)):
                if shutdown:
                    break
                entry_counter += 1
                f = executor.submit(generate_single_entry, entry_counter)
                active_futures[f] = entry_counter

    manifest = load_manifest()
    print("=" * 60)
    print("Execution completed or paused.")
    print(f"Final total entries: {manifest['total_entries']:,}")
    print(f"Final total tokens: {manifest['total_tokens']:,}")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
