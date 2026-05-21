#!/usr/bin/env bash
# scripts/infra-devsecops.sh — Infra DevSecOps checks (CI + local parity)
#
# Runs:
#   - helm lint + render (default + prod overlays)
#   - kubeconform on rendered manifests (core + CRD schemas)
#   - kube-linter on rendered manifests
#   - checkov on Terraform modules
#   - checkov on Helm chart + rendered prod Kubernetes manifests
#
# Usage:
#   bash scripts/infra-devsecops.sh
#
# Optional env:
#   KUBECONFORM_VERSION  (default: v0.6.7)
#   KUBE_LINTER_VERSION  (default: v0.7.1)
#   K8S_VERSION          (default: 1.31.0)
#   CHECKOV_CMD          (default: checkov — use "uv tool run checkov" locally)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELM_CHART="${ROOT}/infra/helm/langgraph-agent-stack"
RENDER_DIR="${RENDER_DIR:-${ROOT}/.infra-render}"
BIN_DIR="${BIN_DIR:-${ROOT}/.infra-tools/bin}"
KUBECONFORM_VERSION="${KUBECONFORM_VERSION:-v0.6.7}"
KUBE_LINTER_VERSION="${KUBE_LINTER_VERSION:-v0.7.1}"
K8S_VERSION="${K8S_VERSION:-1.31.0}"
CHECKOV_CMD="${CHECKOV_CMD:-checkov}"
CRD_SCHEMA_LOCATION="https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"

mkdir -p "${RENDER_DIR}" "${BIN_DIR}"

install_tool() {
  local name="$1" url="$2" bin_name="${3:-$1}"
  if [[ ! -x "${BIN_DIR}/${bin_name}" ]]; then
    echo "[infra-devsecops] Installing ${name}..."
    tmp="$(mktemp -d)"
    curl -sSL "${url}" | tar xz -C "${tmp}"
    install -m 0755 "${tmp}/${bin_name}" "${BIN_DIR}/${bin_name}"
    rm -rf "${tmp}"
  fi
}

install_tool kubeconform \
  "https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}/kubeconform-linux-amd64.tar.gz"
install_tool kube-linter \
  "https://github.com/stackrox/kube-linter/releases/download/${KUBE_LINTER_VERSION}/kube-linter-linux.tar.gz"

export PATH="${BIN_DIR}:${PATH}"

echo "[infra-devsecops] Helm lint"
helm lint "${HELM_CHART}"

echo "[infra-devsecops] Render manifests (default + prod)"
helm template test-release "${HELM_CHART}" > "${RENDER_DIR}/default.yaml"
helm template test-release "${HELM_CHART}" \
  -f "${HELM_CHART}/values.prod.yaml" > "${RENDER_DIR}/prod.yaml"

echo "[infra-devsecops] kubeconform (default)"
kubeconform -summary \
  -kubernetes-version "${K8S_VERSION}" \
  -schema-location default \
  "${RENDER_DIR}/default.yaml"

echo "[infra-devsecops] kubeconform (prod + CRD schemas)"
kubeconform -summary \
  -kubernetes-version "${K8S_VERSION}" \
  -schema-location default \
  -schema-location "${CRD_SCHEMA_LOCATION}" \
  "${RENDER_DIR}/prod.yaml"

echo "[infra-devsecops] kube-linter (default + prod)"
kube-linter lint "${RENDER_DIR}/default.yaml"
kube-linter lint "${RENDER_DIR}/prod.yaml"

echo "[infra-devsecops] checkov — Terraform"
${CHECKOV_CMD} -d "${ROOT}/infra/terraform" --framework terraform --config-file "${ROOT}/.checkov.yaml"

echo "[infra-devsecops] checkov — Helm chart"
${CHECKOV_CMD} -d "${HELM_CHART}" --framework helm --config-file "${ROOT}/.checkov.yaml"

echo "[infra-devsecops] checkov — rendered prod Kubernetes manifests"
${CHECKOV_CMD} -f "${RENDER_DIR}/prod.yaml" --framework kubernetes --config-file "${ROOT}/.checkov.yaml"

echo "[infra-devsecops] All infra DevSecOps checks passed."
