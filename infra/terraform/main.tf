# ---------------------------------------------------------------------------
# Root main.tf — routes to GKE, EKS, or AKS module based on cloud_provider
# ---------------------------------------------------------------------------

locals {
  use_gke = var.cloud_provider == "gke"
  use_eks = var.cloud_provider == "eks"
  use_aks = var.cloud_provider == "azure"
}

# ---------------------------------------------------------------------------
# GKE module — activated when cloud_provider = "gke"
# ---------------------------------------------------------------------------
module "gke" {
  source = "./modules/gke"
  count  = local.use_gke ? 1 : 0

  project_id        = var.project_id
  region            = var.region
  cluster_name      = var.cluster_name
  environment       = var.environment
  namespace         = var.namespace
  helm_chart_path   = var.helm_chart_path
  anthropic_api_key = var.anthropic_api_key
  llm_provider      = var.llm_provider
}

# ---------------------------------------------------------------------------
# EKS module — activated when cloud_provider = "eks"
# ---------------------------------------------------------------------------
module "eks" {
  source = "./modules/eks"
  count  = local.use_eks ? 1 : 0

  aws_region        = var.aws_region
  cluster_name      = var.eks_cluster_name
  environment       = var.environment
  namespace         = var.namespace
  helm_chart_path   = var.helm_chart_path
  anthropic_api_key = var.anthropic_api_key
  llm_provider      = var.llm_provider
}

# ---------------------------------------------------------------------------
# AKS module — activated when cloud_provider = "azure"
# ---------------------------------------------------------------------------
module "aks" {
  source = "./modules/aks"
  count  = local.use_aks ? 1 : 0

  resource_group_name = var.azure_resource_group
  location            = var.azure_location
  cluster_name        = var.azure_cluster_name
  environment         = var.environment
  node_count          = var.node_count
  node_vm_size        = var.azure_node_vm_size
  namespace           = var.namespace
  helm_chart_path     = var.helm_chart_path
  anthropic_api_key   = var.anthropic_api_key
  redis_url           = var.redis_url
  llm_provider        = var.llm_provider

  tags = {
    environment = var.environment
    project     = "langgraph-agent-stack"
    managed-by  = "terraform"
  }
}
