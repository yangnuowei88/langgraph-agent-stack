# ---------------------------------------------------------------------------
# Global variables — shared across GKE, EKS, and AKS modules
# ---------------------------------------------------------------------------

variable "cloud_provider" {
  description = "Target cloud provider for the cluster. Accepted values: 'gke', 'eks', or 'azure'."
  type        = string
  default     = "gke"

  validation {
    condition     = contains(["gke", "eks", "azure"], var.cloud_provider)
    error_message = "cloud_provider must be 'gke', 'eks', or 'azure'."
  }
}

variable "environment" {
  description = "Deployment environment. Accepted values: 'dev' or 'prod'."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

# ---------------------------------------------------------------------------
# LLM / application secrets — never hardcoded
# ---------------------------------------------------------------------------

variable "anthropic_api_key" {
  description = "Anthropic API key injected into the Helm release as a Kubernetes secret. Must never be stored in plaintext."
  type        = string
  sensitive   = true
}

variable "llm_provider" {
  description = "LLM provider used by the agent stack (e.g. anthropic, openai, google)."
  type        = string
  default     = "anthropic"
}

variable "redis_url" {
  description = "Redis connection URL (optional). Required when config.rateLimitBackend = 'redis'."
  type        = string
  sensitive   = true
  default     = ""
}

# ---------------------------------------------------------------------------
# Kubernetes / Helm
# ---------------------------------------------------------------------------

variable "namespace" {
  description = "Kubernetes namespace where the langgraph-agent-stack is deployed."
  type        = string
  default     = "langgraph-agents"
}

variable "helm_chart_path" {
  description = "Relative or absolute path to the langgraph-agent-stack Helm chart directory."
  type        = string
  default     = "../helm/langgraph-agent-stack"
}

variable "node_count" {
  description = "Initial number of nodes (used by AKS; EKS uses node_desired_size)."
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# GKE-specific variables
# ---------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID. Required when cloud_provider = 'gke'."
  type        = string
  default     = ""
}

variable "region" {
  description = "GCP region for the GKE Autopilot cluster."
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Name of the GKE cluster."
  type        = string
  default     = "langgraph-cluster"
}

# ---------------------------------------------------------------------------
# EKS-specific variables
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for the EKS cluster."
  type        = string
  default     = "us-east-1"
}

variable "eks_cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
  default     = "langgraph-cluster"
}

# ---------------------------------------------------------------------------
# AKS-specific variables
# ---------------------------------------------------------------------------

variable "azure_resource_group" {
  description = "Azure Resource Group name. Required when cloud_provider = 'azure'."
  type        = string
  default     = "langgraph-rg"
}

variable "azure_location" {
  description = "Azure region for the AKS cluster (e.g. canadaeast, eastus)."
  type        = string
  default     = "canadaeast"
}

variable "azure_cluster_name" {
  description = "Name of the AKS cluster."
  type        = string
  default     = "langgraph-cluster"
}

variable "azure_node_vm_size" {
  description = "Azure VM size for AKS nodes."
  type        = string
  default     = "Standard_D2s_v3"
}
