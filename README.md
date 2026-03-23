# k8s-copilot

A terminal-based AI copilot for Kubernetes troubleshooting, powered by OpenAI or Anthropic Claude.

Ask questions in plain English and the agent will query your cluster, reason about what it finds, and explain the root cause with concrete remediation steps — no kubectl expertise required.

## Features

- Conversational interface with full multi-turn memory
- Autonomous tool chaining — the agent queries pods, logs, events, deployments, and nodes on its own
- Real-time tool activity display — see what the agent is doing as it reasons
- `diagnose` command — one command scans the entire cluster and summarizes all issues
- Supports both **OpenAI** (gpt-4o) and **Anthropic** (claude-opus-4-6) as LLM backends
- Lockable to a specific kubeconfig context for safety
- Auto-recovers from context window limits by dropping oldest messages

## Requirements

- [pixi](https://pixi.sh) (recommended) or Python 3.11+
- Access to a Kubernetes cluster (local or remote)
- An OpenAI or Anthropic API key

## Installation

```bash
git clone https://github.com/youruser/k8s-copilot.git
cd k8s-copilot
```

Install dependencies with pixi:
```bash
pixi run pip install -e .
```

## Step 1 — Log in to your Kubernetes cluster

Before running k8s-copilot, make sure you are authenticated to your cluster. The exact command depends on your cloud provider:

**AWS EKS:**
```bash
aws eks update-kubeconfig --region <region> --name <cluster-name>
```

**Google GKE:**
```bash
gcloud container clusters get-credentials <cluster-name> --region <region>
```

**Azure AKS:**
```bash
az aks get-credentials --resource-group <resource-group> --name <cluster-name>
```

Verify the connection works:
```bash
kubectl get nodes
```

## Step 2 — Configure

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

| Variable             | Required | Default              | Description                              |
|----------------------|----------|----------------------|------------------------------------------|
| `LLM_PROVIDER`       | No       | `openai`             | `openai` or `anthropic`                  |
| `OPENAI_API_KEY`     | If OpenAI | —                   | Your OpenAI API key                      |
| `OPENAI_MODEL`       | No       | `gpt-4o`             | OpenAI model override                    |
| `ANTHROPIC_API_KEY`  | If Anthropic | —               | Your Anthropic API key                   |
| `ANTHROPIC_MODEL`    | No       | `claude-opus-4-6`    | Anthropic model override                 |
| `KUBECONFIG`         | No       | `~/.kube/config`     | Path to kubeconfig file                  |
| `KUBECONFIG_CONTEXT` | No       | active context       | Lock to a specific kubeconfig context    |
| `GITHUB_TOKEN`       | No       | —                    | GitHub token for issue search (optional) |

## Step 3 — Setting up an isolated kubeconfig (recommended)

By default, k8s-copilot uses your active kubectl context. To lock it to a specific cluster and prevent accidental access to other clusters, create a dedicated kubeconfig file:

**1. Find the context you want to use:**
```bash
kubectl config get-contexts
```

**2. Export just that context into its own file:**
```bash
kubectl config view --minify --context=<context-name> --flatten > ~/.kube/k8s-copilot.kubeconfig
```

The `--minify` flag strips all other contexts, clusters, and credentials, producing a self-contained file with only the target cluster.

**3. Set the env vars in your `.env`:**
```
KUBECONFIG=/Users/you/.kube/k8s-copilot.kubeconfig
KUBECONFIG_CONTEXT=<context-name>
```

## Step 4 — Run

```bash
pixi run k8s-copilot
```

Special commands:
- `diagnose` — scan the entire cluster and report all issues

Example questions:
- `Why are my pods crashing in the payments namespace?`
- `Is anything unhealthy in the cluster?`
- `What's wrong with the auth deployment?`
- `Show me recent warning events`

Type `exit` or press `Ctrl+C` to quit.

## Available tools

### Kubernetes

| Tool               | Description                                      |
|--------------------|--------------------------------------------------|
| `get_pods`         | List pods with status and container states       |
| `describe_pod`     | Detailed pod info, restart counts, exit reasons  |
| `get_pod_logs`     | Fetch logs (supports previous crashed container) |
| `get_events`       | Cluster events, warnings first                   |
| `get_deployments`  | List deployments with replica counts             |
| `get_deployment`   | Detailed deployment info and rollout conditions  |
| `get_nodes`        | Node health, capacity, and conditions            |
| `list_namespaces`  | List all namespaces in the cluster               |
| `get_cronjobs`     | List CronJobs with schedule and last run status  |

### ECR image tracing

| Tool                  | Description                                                                 |
|-----------------------|-----------------------------------------------------------------------------|
| `get_image_git_info`  | Read OCI labels from a private ECR image to extract git commit, branch, and source repo. Falls back to reading the git SHA from the image tag when labels are absent. |
| `find_repo_by_workflow` | Find the GitHub repo that builds a given image by searching `.github/workflows` files for the image name. Used when OCI labels are missing. |

### GitHub

| Tool                      | Description                                                              |
|---------------------------|--------------------------------------------------------------------------|
| `get_commit_info`         | Look up a git commit SHA and find which branches contain it. Scans all branches in parallel. |
| `get_github_file_content` | Fetch lines from a file in a GitHub repo. Supports line ranges (e.g. line 137 from a stack trace) and search term highlighting. |
| `search_github`           | Search GitHub issues for a specific error message                        |
| `search_github_code`      | Search source code in a GitHub repo for an error string                  |
| `search_github_commits`   | Search commit messages in a GitHub repo for an error string              |

## Project structure

```
src/
├── main.py              # CLI entry point
├── agent.py             # LLM backend dispatcher
├── agent_openai.py      # OpenAI implementation
├── agent_anthropic.py   # Anthropic implementation
├── k8s/
│   └── client.py        # Kubernetes client initialisation
└── tools/
    ├── registry.py      # Tool definitions and dispatcher
    ├── utils.py         # Shared error handling
    ├── pods.py
    ├── deployments.py
    ├── events.py
    ├── ecr.py           # ECR image metadata reader (OCI labels)
    └── github.py        # GitHub issue, code, commit, and branch search
    ├── nodes.py
    ├── namespaces.py
    └── cronjobs.py
```