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
ENTRY_TARGET = 10000

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


def gen_fourier_transform_problem():
    n = random.choice([4, 8])
    signal = [random.randint(-10, 10) for _ in range(n)]
    signal_str = ", ".join(map(str, signal))
    problem = (
        f"Given the discrete signal x[n] = {{{signal_str}}} of length N = {n}:\n\n"
        f"1. Compute the Discrete Fourier Transform (DFT) X[k] manually by expanding the summation formula X[k] = Σ x[n] * e^(-j*2π*k*n/N) for each k = 0, 1, ..., {n-1}.\n"
        f"2. Calculate the magnitude spectrum |X[k]| and phase spectrum ∠X[k] for each frequency bin.\n"
        f"3. Verify Parseval's theorem: Σ|x[n]|² = (1/N) Σ|X[k]|².\n"
        f"4. Compute the Inverse DFT to reconstruct x[n] from X[k], confirming perfect reconstruction.\n"
        f"5. If this signal is sampled at {random.choice([8000, 16000, 44100])} Hz, determine the analog frequency corresponding to each spectral bin."
    )
    return "signal_processing_and_transforms", problem


def gen_bayesian_inference_problem():
    prior_a = random.choice([2, 3, 5])
    prior_b = random.choice([3, 5, 7])
    n_trials = random.randint(20, 100)
    n_success = random.randint(5, n_trials - 5)
    problem = (
        f"A pharmaceutical company tests a new drug. Historically, the success rate θ follows a Beta({prior_a}, {prior_b}) prior distribution.\n"
        f"In a clinical trial of {n_trials} patients, {n_success} show positive outcomes.\n\n"
        f"1. Derive the posterior distribution p(θ|data) using Bayes' theorem with the conjugate Beta-Binomial model.\n"
        f"2. Calculate the posterior mean, mode, and 95% credible interval for θ.\n"
        f"3. Compute the posterior predictive probability that the next {random.randint(3, 10)} patients will all show positive outcomes.\n"
        f"4. Perform a Bayes factor analysis comparing H₀: θ ≤ 0.5 vs H₁: θ > 0.5. State your conclusion.\n"
        f"5. Derive the Jeffreys prior for this model and recompute the posterior, comparing it with the informative prior result."
    )
    return "bayesian_statistics_and_inference", problem


def gen_graph_coloring_problem():
    n_nodes = random.choice([5, 6, 7])
    edges = []
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if random.random() < 0.5:
                edges.append((i, j))
    if len(edges) < n_nodes:
        for i in range(n_nodes - 1):
            edges.append((i, i + 1))
        edges = list(set(edges))
    edges_str = ", ".join([f"({u},{v})" for u, v in edges])
    k_colors = random.choice([3, 4])
    problem = (
        f"Consider an undirected graph G = (V, E) with {n_nodes} vertices labeled 0 to {n_nodes-1}.\n"
        f"Edges: E = {{{edges_str}}}\n\n"
        f"1. Determine the chromatic number χ(G) of this graph. Prove your answer by providing a valid coloring and showing fewer colors are impossible.\n"
        f"2. Using the greedy coloring algorithm with vertex ordering 0, 1, ..., {n_nodes-1}, find a valid {k_colors}-coloring (if possible) or prove it cannot be done.\n"
        f"3. Compute the chromatic polynomial P(G, k) for k = {k_colors} using the deletion-contraction method.\n"
        f"4. Determine if G is planar. If it is, verify the four-color theorem. If not, find a K₅ or K₃,₃ subdivision.\n"
        f"5. Calculate the number of distinct valid {k_colors}-colorings accounting for color permutations."
    )
    return "graph_theory_and_coloring", problem


def gen_rsa_cryptography_problem():
    p = random.choice([61, 67, 71, 73, 79, 83, 89, 97])
    q = random.choice([101, 103, 107, 109, 113, 127, 131, 137])
    while q == p:
        q = random.choice([101, 103, 107, 109, 113, 127, 131, 137])
    n = p * q
    phi = (p - 1) * (q - 1)
    e = random.choice([17, 65537])
    problem = (
        f"In the RSA cryptosystem, two primes are chosen as p = {p} and q = {q}.\n\n"
        f"1. Compute n = p * q and Euler's totient φ(n) = (p-1)(q-1).\n"
        f"2. Given public exponent e = {e}, verify that gcd(e, φ(n)) = 1 using the Extended Euclidean Algorithm.\n"
        f"3. Compute the private decryption exponent d such that e * d ≡ 1 (mod φ(n)). Show all steps of the modular inverse computation.\n"
        f"4. Encrypt the message M = {random.randint(2, min(n-1, 5000))} by computing C = M^e mod n using repeated squaring. Show each step.\n"
        f"5. Decrypt C to recover M by computing M = C^d mod n. Verify the original message is recovered.\n"
        f"6. Explain why RSA is secure and discuss the role of integer factorization. What happens if p and q are too close together (Fermat factorization vulnerability)?"
    )
    return "number_theory_and_rsa", problem


def gen_heat_equation_problem():
    L = random.choice([1, 2, 3])
    alpha = round(random.uniform(0.1, 2.0), 2)
    T_0 = random.randint(50, 200)
    n_terms = random.choice([3, 5])
    problem = (
        f"Solve the 1D heat equation ∂u/∂t = {alpha} * ∂²u/∂x² on the domain 0 ≤ x ≤ {L}, t ≥ 0 with:\n"
        f"- Boundary conditions: u(0, t) = 0, u({L}, t) = 0 (Dirichlet)\n"
        f"- Initial condition: u(x, 0) = {T_0} * sin(πx/{L}) + {random.randint(20, 80)} * sin(3πx/{L})\n\n"
        f"1. Apply separation of variables u(x,t) = X(x)T(t) and derive the general solution as a Fourier sine series.\n"
        f"2. Apply the initial condition to find all Fourier coefficients. Show the orthogonality integrals explicitly.\n"
        f"3. Write the complete solution with the first {n_terms} terms of the series.\n"
        f"4. Calculate the temperature at x = {L}/2, t = {round(random.uniform(0.1, 2.0), 2)} to 4 decimal places.\n"
        f"5. Determine the thermal diffusivity time constant and estimate when the system reaches 99% of steady state."
    )
    return "partial_differential_equations", problem


def gen_quantum_circuit_problem():
    problem = (
        f"Design and analyze a quantum circuit for the following task:\n\n"
        f"1. Construct a 2-qubit quantum circuit that implements the Controlled-NOT (CNOT) gate using only single-qubit gates (H, T, T†) and CNOT gates. Draw the circuit diagram.\n"
        f"2. Starting from the state |00⟩, apply a Hadamard gate to qubit 1, then a CNOT gate (control=qubit 1, target=qubit 2). Write the resulting 4-dimensional state vector.\n"
        f"3. Prove this creates a maximally entangled Bell state by computing the reduced density matrix of each qubit and showing the von Neumann entropy is log(2).\n"
        f"4. Design a quantum circuit for the Deutsch-Jozsa algorithm with {random.choice([2, 3])} qubits. Prove it determines whether f is constant or balanced in a single query.\n"
        f"5. Implement the quantum Fourier transform (QFT) for {random.choice([2, 3])} qubits. Write the unitary matrix and verify it is unitary (U†U = I).\n"
        f"6. Calculate the circuit depth and gate count of your QFT implementation and compare with the classical FFT complexity."
    )
    return "quantum_computing_and_circuits", problem


def gen_neural_network_backprop_problem():
    layers = random.choice([[2, 3, 1], [2, 4, 2, 1], [3, 5, 3, 1]])
    layers_str = " → ".join(map(str, layers))
    lr = round(random.uniform(0.01, 0.5), 2)
    problem = (
        f"Consider a fully-connected feedforward neural network with architecture: {layers_str} (input → hidden → output).\n"
        f"Use the sigmoid activation function σ(z) = 1/(1+e^(-z)) for all layers and mean squared error loss.\n\n"
        f"1. Initialize all weights from Uniform(-0.5, 0.5) and biases to 0. Write the forward pass equations layer by layer.\n"
        f"2. Given input x = [{round(random.uniform(0, 1), 2)}, {round(random.uniform(0, 1), 2)}] and target y = {round(random.uniform(0, 1), 2)}, compute the network output and loss.\n"
        f"3. Derive the backpropagation equations from scratch using the chain rule. Compute ∂L/∂w and ∂L/∂b for every weight and bias in the network.\n"
        f"4. Perform one step of gradient descent with learning rate η = {lr}. Report the updated weights.\n"
        f"5. Recompute the loss after the weight update. Did the loss decrease? If not, explain why and what learning rate adjustments are needed.\n"
        f"6. Derive the vanishing gradient problem: compute the gradient magnitude at the first layer and explain why deep networks with sigmoid activations train slowly."
    )
    return "neural_network_architecture_and_training", problem


def gen_circuit_analysis_problem():
    V = random.choice([5, 9, 12, 24])
    R1 = random.choice([100, 220, 330, 470, 1000])
    R2 = random.choice([100, 220, 330, 470, 1000])
    R3 = random.choice([100, 220, 330, 470, 1000])
    problem = (
        f"Analyze the following electrical circuit using Kirchhoff's laws:\n"
        f"- A voltage source V = {V}V is connected in series with resistor R₁ = {R1}Ω.\n"
        f"- After R₁, the circuit splits into two parallel branches:\n"
        f"  Branch A: R₂ = {R2}Ω\n"
        f"  Branch B: R₃ = {R3}Ω in series with a second voltage source V₂ = {random.choice([3, 5])}V (opposing polarity)\n"
        f"- The parallel branches rejoin and return to the main source.\n\n"
        f"1. Draw the circuit and label all components, currents, and voltage drops.\n"
        f"2. Apply Kirchhoff's Voltage Law (KVL) to write the loop equations for both independent loops.\n"
        f"3. Apply Kirchhoff's Current Law (KCL) at the junction node.\n"
        f"4. Solve the system of linear equations to find all branch currents I₁, I₂, I₃.\n"
        f"5. Calculate the power dissipated in each resistor and the power supplied by each source.\n"
        f"6. Verify conservation of energy: total power supplied = total power dissipated.\n"
        f"7. Compute the Thevenin equivalent circuit as seen from R₂'s terminals."
    )
    return "electrical_circuit_analysis", problem


def gen_automata_theory_problem():
    n_states = random.choice([3, 4])
    alphabet = ['a', 'b']
    transitions = {}
    for s in range(n_states):
        for c in alphabet:
            transitions[(s, c)] = random.randint(0, n_states - 1)
    accept_states = random.sample(range(n_states), random.randint(1, n_states - 1))
    trans_str = "\n".join([f"  δ({s}, '{c}') = {t}" for (s, c), t in sorted(transitions.items())])
    problem = (
        f"Consider a Deterministic Finite Automaton (DFA) M = (Q, Σ, δ, q₀, F) where:\n"
        f"- Q = {{q₀, q₁, ...q{n_states-1}}}\n"
        f"- Σ = {{a, b}}\n"
        f"- q₀ is the start state\n"
        f"- F = {{{', '.join([f'q{s}' for s in accept_states])}}}\n"
        f"- Transition function δ:\n{trans_str}\n\n"
        f"1. Draw the state transition diagram for this DFA.\n"
        f"2. Construct the transition table and determine if each of these strings is accepted: 'abba', 'bab', '{''.join(random.choices(alphabet, k=random.randint(3, 6)))}'.\n"
        f"3. Construct the complement DFA M̄ that accepts exactly the strings rejected by M.\n"
        f"4. Convert this DFA to a regular expression using the state elimination method. Show each elimination step.\n"
        f"5. Construct an equivalent NFA with fewer states (if possible) and prove equivalence.\n"
        f"6. Apply the Myhill-Nerode theorem to determine the minimum-state DFA equivalent to M. Identify all distinguishable state pairs."
    )
    return "automata_and_formal_languages", problem


def gen_portfolio_optimization_problem():
    n_assets = random.choice([3, 4])
    returns = [round(random.uniform(0.02, 0.15), 4) for _ in range(n_assets)]
    variances = [round(random.uniform(0.01, 0.08), 4) for _ in range(n_assets)]
    correlations = []
    for i in range(n_assets):
        row = []
        for j in range(n_assets):
            if i == j:
                row.append(1.0)
            elif j > i:
                row.append(round(random.uniform(-0.3, 0.7), 2))
            else:
                row.append(correlations[j][i])
        correlations.append(row)
    cov_matrix = []
    for i in range(n_assets):
        row = []
        for j in range(n_assets):
            row.append(round(variances[i] ** 0.5 * variances[j] ** 0.5 * correlations[i][j], 6))
        cov_matrix.append(row)
    problem = (
        f"Consider a portfolio optimization problem with {n_assets} assets.\n"
        f"Expected annual returns: μ = {returns}\n"
        f"Variances: σ² = {variances}\n"
        f"Covariance matrix Σ:\n"
        + "\n".join([f"  [{', '.join([f'{v:.4f}' for v in row])}]" for row in cov_matrix]) +
        f"\n\n"
        f"1. Formulate the Markowitz mean-variance optimization as a quadratic programming problem: minimize w^T Σ w subject to w^T μ = μ_target and Σwᵢ = 1.\n"
        f"2. Derive the efficient frontier analytically using Lagrange multipliers. Show all matrix algebra.\n"
        f"3. Find the minimum variance portfolio weights and its expected return and risk.\n"
        f"4. If the risk-free rate is {round(random.uniform(0.01, 0.04), 3)}, find the tangency portfolio (maximum Sharpe ratio).\n"
        f"5. Plot the efficient frontier and identify the capital market line.\n"
        f"6. Apply the Black-Litterman model: if an investor believes Asset 1 will return {round(random.uniform(0.05, 0.20), 2)} with {round(random.uniform(0.3, 0.8), 2)} confidence, derive the adjusted equilibrium returns."
    )
    return "portfolio_optimization_and_finance", problem


def gen_monte_carlo_integration_problem():
    dim = random.choice([2, 3])
    n_samples = random.choice([10000, 100000])
    if dim == 2:
        func_str = f"f(x,y) = exp(-(x² + y²))"
        region = "unit disk x² + y² ≤ 1"
    else:
        func_str = f"f(x,y,z) = exp(-(x² + y² + z²))"
        region = "unit sphere x² + y² + z² ≤ 1"
    problem = (
        f"Estimate the integral of {func_str} over the {region} using Monte Carlo methods.\n\n"
        f"1. Derive the crude Monte Carlo estimator: I ≈ (V/N) Σ f(xᵢ), where V is the volume of the region. State the theoretical variance of this estimator.\n"
        f"2. Implement importance sampling using a Gaussian proposal distribution N(0, σ²I). Derive the optimal σ and the resulting variance reduction ratio.\n"
        f"3. Generate {n_samples} uniform random samples inside the region using rejection sampling. Calculate the acceptance ratio.\n"
        f"4. Compute the integral estimate, standard error, and 95% confidence interval from your samples.\n"
        f"5. Compare with the analytical result (which involves the error function). Calculate the relative error.\n"
        f"6. Implement stratified sampling by dividing the region into {random.choice([4, 8, 16])} equal-volume strata. Show the variance reduction compared to crude Monte Carlo."
    )
    return "numerical_methods_and_monte_carlo", problem


def gen_wave_equation_problem():
    L = random.choice([1, 2])
    c = random.choice([1, 2, 3])
    n_modes = random.choice([3, 5])
    problem = (
        f"Solve the 1D wave equation ∂²u/∂t² = {c}² * ∂²u/∂x² on 0 ≤ x ≤ {L}, t ≥ 0 with:\n"
        f"- Boundary conditions: u(0, t) = 0, u({L}, t) = 0 (fixed ends)\n"
        f"- Initial conditions: u(x, 0) = {random.randint(1, 5)} * sin(πx/{L}) + {random.randint(1, 3)} * sin(2πx/{L})\n"
        f"  ∂u/∂t(x, 0) = 0 (released from rest)\n\n"
        f"1. Apply separation of variables and derive the general solution as a superposition of normal modes.\n"
        f"2. Compute all Fourier coefficients from the initial conditions. Show the orthogonality integrals.\n"
        f"3. Write the complete solution with the first {n_modes} modes.\n"
        f"4. Calculate the fundamental frequency and all harmonic frequencies of this vibrating string.\n"
        f"5. Compute the total energy E = ∫(½(∂u/∂t)² + ½c²(∂u/∂x)²)dx and prove it is conserved over time.\n"
        f"6. At what time t > 0 does the string first return exactly to its initial shape? Prove your answer."
    )
    return "wave_physics_and_acoustics", problem


THEORETICAL_TOPICS = [
    "geometry_and_topology", "relativity_and_astrophysics", "thermodynamics_and_statistical_mechanics",
    "particle_and_nuclear_physics", "organic_and_physical_chemistry", "biochemistry_and_molecular_biology",
    "genetics_and_bioinformatics", "algorithms_and_complexity", "data_structures_and_databases",
    "distributed_systems_and_cloud", "cryptography_and_security", "compilers_and_programming_languages",
    "artificial_intelligence_and_ml", "operating_systems_and_networking", "formal_logic_and_set_theory",
    "analytical_philosophy_and_epistemology", "game_theory_and_decision_theory", "linguistics_and_formal_semantics",
    "quantitative_finance_and_economics", "control_systems_and_information_theory",
    "signal_processing_and_transforms", "bayesian_statistics_and_inference", "graph_theory_and_coloring",
    "number_theory_and_rsa", "partial_differential_equations", "quantum_computing_and_circuits",
    "neural_network_architecture_and_training", "electrical_circuit_analysis", "automata_and_formal_languages",
    "portfolio_optimization_and_finance", "numerical_methods_and_monte_carlo", "wave_physics_and_acoustics"
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
    ],
    "signal_processing_and_transforms": [
        "deriving the Fast Fourier Transform (FFT) algorithm and analyzing its computational complexity",
        "proving the Nyquist-Shannon sampling theorem and deriving anti-aliasing filter specifications",
        "designing FIR and IIR digital filters using windowing methods (Hamming, Kaiser)",
        "deriving the Short-Time Fourier Transform (STFT) and analyzing the time-frequency uncertainty principle",
        "implementing the Welch method for power spectral density estimation from noisy signals",
        "designing adaptive filters using the Least Mean Squares (LMS) algorithm",
        "deriving the Wavelet transform and constructing multi-resolution analysis using Daubechies wavelets",
        "analyzing the Z-transform and deriving the transfer function of discrete-time systems",
        "designing Kalman-Bucy filters for optimal linear filtering of stochastic signals",
        "deriving the cepstral analysis method for speech processing and homomorphic deconvolution",
        "proving the convolution theorem and its applications in fast polynomial multiplication",
        "designing matched filters for optimal signal detection in additive white Gaussian noise",
        "analyzing compressed sensing theory and proving RIP (Restricted Isometry Property) conditions",
        "deriving MUSIC and ESPRIT algorithms for high-resolution direction-of-arrival estimation",
        "implementing the Goertzel algorithm for efficient single-frequency DFT computation",
        "designing multirate signal processing systems (decimation, interpolation, polyphase filters)",
        "deriving the discrete cosine transform (DCT) and its application in JPEG compression",
        "analyzing cyclostationary signal processing and spectral correlation functions",
        "designing beamforming algorithms for phased array antenna systems",
        "deriving the Chirp Z-transform and its advantages over standard DFT for zoom-in analysis"
    ],
    "bayesian_statistics_and_inference": [
        "deriving the posterior predictive distribution for hierarchical Bayesian models",
        "implementing Markov Chain Monte Carlo (MCMC) using the Metropolis-Hastings algorithm",
        "designing Bayesian neural networks with weight uncertainty using variational inference",
        "deriving the Evidence Lower Bound (ELBO) for Variational Autoencoders",
        "implementing Gibbs sampling for Bayesian Gaussian mixture models",
        "proving convergence guarantees of MCMC chains using ergodic theory",
        "designing Bayesian optimization with Gaussian process surrogates for black-box functions",
        "deriving the Bayesian information criterion (BIC) and comparing with AIC for model selection",
        "implementing Hamiltonian Monte Carlo (HMC) and the No-U-Turn Sampler (NUTS)",
        "analyzing Bayesian hypothesis testing using Bayes factors and Savage-Dickey density ratios",
        "designing Bayesian clinical trials with adaptive sample size re-estimation",
        "deriving empirical Bayes estimates using the James-Stein shrinkage estimator",
        "implementing particle filters (Sequential Monte Carlo) for state-space models",
        "proving the Bernstein-von Mises theorem on posterior asymptotic normality",
        "designing Bayesian nonparametric models using the Dirichlet Process",
        "deriving conjugate prior families for exponential family distributions",
        "implementing expectation propagation (EP) for approximate Bayesian inference",
        "analyzing prior sensitivity and deriving robust Bayesian methods using ε-contamination classes",
        "designing Bayesian optimization for hyperparameter tuning of deep learning models",
        "deriving the posterior distribution for Gaussian process regression with noisy observations"
    ],
    "graph_theory_and_coloring": [
        "proving Brooks' theorem on the chromatic number of connected graphs",
        "deriving the Tutte polynomial and calculating it for specific graph families",
        "proving the max-flow min-cut theorem using linear programming duality",
        "designing approximation algorithms for the maximum independent set problem",
        "deriving spectral graph theory bounds using eigenvalues of the adjacency matrix",
        "proving Hall's marriage theorem and its applications to bipartite matching",
        "implementing the Hopcroft-Karp algorithm for maximum bipartite matching",
        "analyzing random graphs (Erdős-Rényi model) and proving threshold phenomena",
        "deriving the matrix tree theorem for counting spanning trees",
        "proving Vizing's theorem: every simple graph has edge-chromatic number Δ or Δ+1",
        "designing algorithms for finding minimum dominating sets in graphs",
        "implementing Dijkstra's and A* algorithms and analyzing optimality conditions",
        "proving Dilworth's theorem on chain decompositions of partially ordered sets",
        "analyzing expander graphs and proving their spectral gap properties",
        "deriving the genus of a graph and embedding it on higher-genus surfaces",
        "designing algorithms for graph isomorphism testing (Weisfeiler-Leman refinement)",
        "proving the Hajós conjecture for specific graph classes",
        "implementing the Stoer-Wagner algorithm for minimum global cut",
        "analyzing network centrality measures (betweenness, closeness, eigenvector)",
        "deriving the relationship between treewidth and graph minor theory"
    ],
    "number_theory_and_rsa": [
        "proving the Miller-Rabin primality test and analyzing its error probability",
        "implementing the AKS primality test and proving its polynomial-time complexity",
        "deriving the quadratic sieve algorithm for integer factorization",
        "proving the law of quadratic reciprocity using Gauss sums",
        "implementing elliptic curve factorization method (Lenstra's ECM)",
        "deriving the Riemann zeta function's Euler product formula and its connection to primes",
        "proving Dirichlet's theorem on primes in arithmetic progressions",
        "implementing the baby-step giant-step algorithm for discrete logarithms",
        "deriving the Pohlig-Hellman algorithm for discrete logarithms in composite-order groups",
        "proving the Chinese Remainder Theorem constructively and analyzing computational complexity",
        "implementing Schoof's algorithm for counting points on elliptic curves over finite fields",
        "deriving the number field sieve and analyzing its sub-exponential complexity",
        "proving Fermat's Last Theorem for n=3 using infinite descent",
        "analyzing pseudorandom number generators based on the Blum-Blum-Shub construction",
        "deriving continued fraction expansions and their application to Pell's equation",
        "implementing the Lenstra-Lenstra-Lovász (LLL) lattice reduction algorithm",
        "proving the prime number theorem using complex analytic methods",
        "deriving modular forms and their connection to elliptic curves (modularity theorem)",
        "analyzing the security of Diffie-Hellman key exchange under the discrete log assumption",
        "implementing Paillier homomorphic encryption and proving its semantic security"
    ],
    "partial_differential_equations": [
        "solving the 2D Laplace equation on a rectangular domain using separation of variables",
        "deriving the method of characteristics for first-order quasi-linear PDEs",
        "solving the Burgers' equation using the Cole-Hopf transformation",
        "proving existence and uniqueness of solutions to the Navier-Stokes equations (weak solutions)",
        "deriving finite difference schemes for the heat equation and analyzing stability (CFL condition)",
        "implementing the finite element method (FEM) for 2D Poisson equation on triangular meshes",
        "solving the Schrödinger equation for the hydrogen atom and deriving orbital shapes",
        "deriving the Green's function for the Helmholtz equation in 2D and 3D",
        "analyzing shock wave formation in the inviscid Burgers' equation using Rankine-Hugoniot conditions",
        "implementing spectral methods for solving PDEs using Chebyshev collocation",
        "deriving the variational formulation of elasticity theory (Lamé equations)",
        "solving the Black-Scholes PDE for European option pricing using Crank-Nicolson scheme",
        "proving maximum principles for harmonic functions and their applications",
        "deriving the weak formulation of elliptic PDEs and proving Lax-Milgram theorem",
        "implementing multigrid methods for solving large sparse systems from PDE discretization",
        "analyzing dispersive wave equations and deriving the group velocity dispersion relation",
        "solving the Fokker-Planck equation for Brownian motion with drift",
        "deriving level set methods for tracking moving interfaces and fronts",
        "implementing immersed boundary methods for fluid-structure interaction problems",
        "proving regularity estimates for solutions of second-order elliptic PDEs"
    ],
    "quantum_computing_and_circuits": [
        "deriving the quantum teleportation protocol and proving its fidelity is unity",
        "implementing Shor's algorithm for factoring 15 on a quantum circuit simulator",
        "proving the no-cloning theorem and its implications for quantum cryptography",
        "designing quantum error correction codes (Shor code, Steane code, surface codes)",
        "deriving Grover's search algorithm and proving the quadratic speedup is optimal",
        "implementing the Variational Quantum Eigensolver (VQE) for molecular ground state energy",
        "proving quantum entanglement violates Bell inequalities (CHSH inequality)",
        "designing quantum approximate optimization algorithm (QAOA) for MaxCut",
        "deriving the density matrix formalism and quantum channel representations (Kraus operators)",
        "implementing quantum phase estimation for eigenvalue problems",
        "proving the Solovay-Kitaev theorem for universal quantum gate approximation",
        "designing topological quantum computing using anyonic braiding operations",
        "deriving quantum key distribution (BB84 protocol) and proving its information-theoretic security",
        "implementing the Harrow-Hassidim-Lloyd (HHL) algorithm for linear systems",
        "analyzing quantum decoherence models (amplitude damping, phase damping channels)",
        "deriving the stabilizer formalism for quantum error-correcting codes",
        "designing quantum walk algorithms for graph search problems",
        "proving the Gottesman-Knill theorem for efficient classical simulation of Clifford circuits",
        "implementing variational quantum classifiers for machine learning tasks",
        "deriving the threshold theorem for fault-tolerant quantum computation"
    ],
    "neural_network_architecture_and_training": [
        "deriving the universal approximation theorem for single-hidden-layer networks",
        "proving convergence guarantees of SGD for non-convex neural network optimization",
        "designing residual networks (ResNet) and deriving the gradient flow through skip connections",
        "implementing the Transformer architecture from scratch including multi-head attention",
        "deriving batch normalization equations and analyzing internal covariate shift",
        "designing Graph Neural Networks (GNNs) using message passing neural network framework",
        "implementing contrastive learning (SimCLR, MoCo) and deriving the InfoNCE loss",
        "deriving the reparameterization trick for training variational autoencoders",
        "designing neural architecture search (NAS) using differentiable architecture search (DARTS)",
        "proving Lipschitz bounds of neural networks and their implications for robustness",
        "implementing Mixture of Experts (MoE) models and deriving the load balancing loss",
        "deriving the attention mechanism mathematically and analyzing its computational complexity",
        "designing normalizing flows (RealNVP, Glow) for tractable density estimation",
        "implementing reinforcement learning from human feedback (RLHF) with PPO",
        "deriving the neural tangent kernel (NTK) for infinite-width network analysis",
        "designing diffusion models (DDPM) and deriving the variational lower bound",
        "implementing knowledge distillation for model compression with temperature scaling",
        "deriving spectral normalization for stabilizing GAN training",
        "designing vision transformers (ViT) and analyzing patch embedding mathematics",
        "proving memorization capacity bounds for overparameterized neural networks"
    ],
    "electrical_circuit_analysis": [
        "deriving the mesh analysis and nodal analysis methods for AC circuits with phasors",
        "designing active filters (Butterworth, Chebyshev) using operational amplifiers",
        "analyzing transistor amplifier circuits (CE, CB, CC) using small-signal models",
        "deriving the telegrapher's equations for transmission line analysis",
        "designing switching power supply circuits (buck, boost, buck-boost converters)",
        "analyzing mutual inductance and transformer equivalent circuits",
        "deriving the two-port network parameters (Z, Y, ABCD, S parameters)",
        "designing oscillator circuits (Colpitts, Hartley, Wien bridge) and analyzing startup conditions",
        "analyzing CMOS inverter circuits and deriving the voltage transfer characteristic",
        "designing differential amplifier circuits and calculating CMRR",
        "deriving the maximum power transfer theorem for AC circuits with complex impedances",
        "analyzing three-phase power systems and calculating balanced/unbalanced loads",
        "designing PLL (phase-locked loop) circuits and analyzing loop dynamics",
        "deriving the Miller effect and its impact on amplifier bandwidth",
        "analyzing diode circuits (clippers, clampers, rectifiers) with piecewise linear models",
        "designing current mirror circuits for integrated circuit biasing",
        "deriving the noise figure cascade formula for multi-stage amplifier chains",
        "analyzing sampling circuits and deriving the aperture jitter noise limits",
        "designing impedance matching networks using Smith chart analysis",
        "deriving switching transient analysis for RL and RC circuits with time-varying sources"
    ],
    "automata_and_formal_languages": [
        "proving the pumping lemma for regular languages and using it to show non-regularity",
        "deriving the Chomsky normal form conversion for context-free grammars",
        "proving the undecidability of the halting problem using diagonalization",
        "implementing the CYK parsing algorithm for context-free grammars",
        "deriving Rabin's theorem: all properties of regular languages are decidable",
        "proving Rice's theorem and its implications for program verification",
        "designing pushdown automata for context-free languages and proving equivalence with CFGs",
        "implementing the Earley parser for general context-free grammars",
        "proving the equivalence of Turing machines and lambda calculus (Church-Turing thesis)",
        "deriving the Chomsky hierarchy and proving strict containment of language classes",
        "designing two-way finite automata and proving they recognize only regular languages",
        "implementing Brzozowski's algorithm for DFA minimization using derivatives",
        "proving Savitch's theorem: NSPACE(s(n)) ⊆ DSPACE(s(n)²)",
        "deriving the Immerman-Szelepcsényi theorem: NL = coNL",
        "designing alternating Turing machines and analyzing the alternation hierarchy",
        "proving the Cook-Levin theorem with full reduction from NP to SAT",
        "implementing tree automata for XML document validation",
        "deriving Büchi automata for linear temporal logic (LTL) model checking",
        "proving the decidability of Presburger arithmetic and its complexity",
        "designing quantum finite automata and comparing with classical language recognition"
    ],
    "portfolio_optimization_and_finance": [
        "deriving the Capital Asset Pricing Model (CAPM) from market equilibrium",
        "proving the fundamental theorem of asset pricing (no-arbitrage ⟵⟹ equivalent martingale measure)",
        "deriving the Heston stochastic volatility model and semi-analytical option pricing",
        "implementing Monte Carlo simulation for pricing path-dependent exotic options",
        "deriving the Vasicek and Cox-Ingersoll-Ross interest rate models",
        "proving the put-call parity and deriving bounds on option prices",
        "designing delta-hedging strategies and deriving the Greeks (delta, gamma, vega, theta, rho)",
        "deriving the Kelly criterion for optimal bet sizing in repeated investments",
        "implementing the binomial options pricing model and proving convergence to Black-Scholes",
        "analyzing credit risk using the Merton structural model and deriving default probabilities",
        "deriving the Heath-Jarrow-Morton (HJM) framework for forward rate modeling",
        "implementing Value at Risk (VaR) and Conditional VaR using historical and parametric methods",
        "deriving the Garman-Kohlhagen model for foreign exchange option pricing",
        "analyzing market microstructure models and deriving optimal execution algorithms",
        "proving the efficient market hypothesis implications using martingale theory",
        "deriving the Fama-French three-factor and five-factor asset pricing models",
        "implementing copula models for multivariate dependency in financial returns",
        "designing risk parity portfolios and deriving the equal risk contribution algorithm",
        "deriving the SABR model for stochastic volatility smile interpolation",
        "analyzing jump-diffusion models (Merton, Kou) and deriving characteristic functions for pricing"
    ],
    "numerical_methods_and_monte_carlo": [
        "proving convergence rates of Newton's method for non-linear systems",
        "implementing the Runge-Kutta-Fehlberg adaptive step-size ODE solver",
        "deriving the conjugate gradient method for symmetric positive definite systems",
        "proving stability and convergence of finite difference schemes for hyperbolic PDEs",
        "implementing the Nelder-Mead simplex method for derivative-free optimization",
        "deriving Gaussian quadrature rules and proving optimal polynomial exactness",
        "implementing the Arnoldi iteration for large-scale eigenvalue problems",
        "proving the convergence of the Jacobi and Gauss-Seidel iterative methods",
        "deriving Richardson extrapolation and its application to Romberg integration",
        "implementing the biconjugate gradient stabilized (BiCGSTAB) method for non-symmetric systems",
        "proving the Lax equivalence theorem: consistency + stability ⟺ convergence",
        "deriving spline interpolation (cubic, B-spline) and proving minimum curvature property",
        "implementing the simplex method for linear programming and analyzing pivot strategies",
        "proving the convergence of simulated annealing using Markov chain theory",
        "deriving the fast multipole method (FMM) for N-body gravitational simulations",
        "implementing Anderson acceleration for fixed-point iterations",
        "proving error bounds for polynomial interpolation (Runge's phenomenon, Chebyshev nodes)",
        "deriving the boundary element method (BEM) for solving Laplace equation",
        "implementing automatic differentiation (forward and reverse mode) from scratch",
        "deriving randomized SVD algorithms and proving approximation guarantees"
    ],
    "wave_physics_and_acoustics": [
        "deriving the Doppler effect for both source and observer motion in 3D",
        "solving the electromagnetic wave equation from Maxwell's equations in vacuum",
        "deriving Fresnel equations for reflection and transmission at dielectric interfaces",
        "analyzing diffraction patterns using the Fraunhofer and Fresnel approximations",
        "deriving the acoustic wave equation in heterogeneous media",
        "proving Snell's law from Fermat's principle of least time",
        "designing impedance matching layers for ultrasonic transducers",
        "deriving the dispersion relation for surface waves (Rayleigh waves) on elastic solids",
        "analyzing wave propagation in periodic structures (photonic crystals, Bragg gratings)",
        "deriving the Korteweg-de Vries (KdV) equation for shallow water solitary waves",
        "implementing the finite-difference time-domain (FDTD) method for electromagnetic simulation",
        "proving the reciprocity theorem for acoustic and electromagnetic waves",
        "deriving the beam propagation method for paraxial wave optics",
        "analyzing normal modes of vibration in rectangular and circular cavities",
        "deriving the Lippmann-Schwinger equation for acoustic scattering problems",
        "designing acoustic metamaterials with negative effective density and bulk modulus",
        "deriving the Bloch theorem for wave propagation in periodic media",
        "analyzing nonlinear wave phenomena: harmonic generation and self-phase modulation",
        "deriving the WKB approximation for wave propagation in slowly varying media",
        "implementing boundary element methods for acoustic radiation and scattering"
    ]
}

PROMPT_TEMPLATES = [
    "Analyze and solve this challenging problem in detail: {sub_topic}. Focus on a rigorous mathematical or technical walkthrough. Think step by step and present your full logical reasoning trace before giving the final solution.",
    "Draft a comprehensive, highly technical analysis of {sub_topic}. Include a thorough mathematical or structural breakdown, investigate edge cases, explain your internal model and assumptions, and formulate the exact reasoning trace.",
    "Formulate a complete proof or systemic design for the following topic: {sub_topic}. Provide a step-by-step logical derivation of every lemma, axiom, or engineering trade-off. Show all intermediate steps and detail your thinking process clearly.",
    "Deconstruct {sub_topic} down to its fundamental principles. Propose a complex scenario or concrete math puzzle within this area, then solve it rigorously. Make sure to detail your internal reasoning, corrections, and logical flow.",
    "Provide an expert-level, detailed tutorial solving {sub_topic}. Frame a difficult, non-trivial hypothetical problem first, then detail the step-by-step mathematical or architectural reasoning to resolve it.",
    "You are a professor writing a graduate-level exam question on {sub_topic}. First, design a challenging multi-part problem that tests deep understanding. Then solve it completely, showing every derivation, proof step, and edge case analysis.",
    "I need an exhaustive technical reference on {sub_topic}. Start from first principles, derive all key equations or algorithms from scratch, prove correctness or convergence where applicable, and illustrate with a concrete worked example.",
    "Simulate being a senior researcher peer-reviewing a paper on {sub_topic}. Identify the hardest open question or most subtle technical challenge in this area, then provide a complete solution with full mathematical rigor.",
    "Build a complete case study around {sub_topic}. Define a realistic scenario with specific parameters, then walk through the entire solution process: modeling, analysis, computation, verification, and interpretation of results.",
    "Treat {sub_topic} as a systems design challenge. Start with requirements gathering, then perform a rigorous mathematical or algorithmic analysis of the design space, prove optimality of your chosen approach, and validate with detailed calculations."
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
    gen_fourier_transform_problem,
    gen_bayesian_inference_problem,
    gen_graph_coloring_problem,
    gen_rsa_cryptography_problem,
    gen_heat_equation_problem,
    gen_quantum_circuit_problem,
    gen_neural_network_backprop_problem,
    gen_circuit_analysis_problem,
    gen_automata_theory_problem,
    gen_portfolio_optimization_problem,
    gen_monte_carlo_integration_problem,
    gen_wave_equation_problem,
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
