# ARIA — Azure Deployment Guide

## Prerequisites

- Azure CLI installed and logged in (`az login`)
- Docker installed locally
- Environment variables set (see `.env.prod`)

## Variables

```bash
export RESOURCE_GROUP=aria-rg
export LOCATION=francecentral
export ACR_NAME=ariacr
export ENVIRONMENT=aria-env
export IMAGE_TAG=latest
```

## 1. Create Resource Group

```bash
az group create --name $RESOURCE_GROUP --location $LOCATION
```

## 2. Create Azure Container Registry

```bash
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

## 3. Build and Push Images

```bash
az acr login --name $ACR_NAME

docker build -f docker/api.prod.Dockerfile -t $ACR_NAME.azurecr.io/aria-api:$IMAGE_TAG .
docker build -f docker/worker.prod.Dockerfile -t $ACR_NAME.azurecr.io/aria-worker:$IMAGE_TAG .

docker push $ACR_NAME.azurecr.io/aria-api:$IMAGE_TAG
docker push $ACR_NAME.azurecr.io/aria-worker:$IMAGE_TAG
```

## 4. Create Container Apps Environment

```bash
az containerapp env create \
  --name $ENVIRONMENT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

## 5. Deploy API Container App

```bash
az containerapp create \
  --name aria-api \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT \
  --image $ACR_NAME.azurecr.io/aria-api:$IMAGE_TAG \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-username $(az acr credential show --name $ACR_NAME --query username -o tsv) \
  --registry-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv) \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    DATABASE_URL=secretref:database-url \
    REDIS_URL=secretref:redis-url \
    AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint \
    AZURE_OPENAI_API_KEY=secretref:openai-key \
    AZURE_OPENAI_MODEL=gpt-4o-mini \
    AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small \
    AZURE_OPENAI_API_VERSION=2024-08-01-preview
```

## 6. Deploy Worker Container App

```bash
az containerapp create \
  --name aria-worker \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT \
  --image $ACR_NAME.azurecr.io/aria-worker:$IMAGE_TAG \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-username $(az acr credential show --name $ACR_NAME --query username -o tsv) \
  --registry-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv) \
  --min-replicas 1 \
  --max-replicas 2 \
  --env-vars \
    DATABASE_URL=secretref:database-url \
    REDIS_URL=secretref:redis-url \
    AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint \
    AZURE_OPENAI_API_KEY=secretref:openai-key
```

## 7. Get API URL

```bash
az containerapp show \
  --name aria-api \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv
```
