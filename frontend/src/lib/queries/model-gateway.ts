// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { ErrorResponse, OkResponse } from "@/types/api";

export interface MediaRelayConfig {
  source: string;
  provider: string;
  ttlSeconds: number;
  endpoint: string;
  bucket: string;
  accessKeyIdPreview: string;
  accessKeySecretPreview: string;
  cloudName?: string;
  cloudinaryApiKeyPreview?: string;
  cloudinaryApiSecretPreview?: string;
  apiFolder?: string;
  configured: boolean;
}

export interface SaveMediaRelayConfigInput {
  provider: string;
  ttlSeconds: number;
  endpoint?: string;
  bucket?: string;
  accessKeyId?: string;
  accessKeySecret?: string;
  cloudName?: string;
  apiKey?: string;
  apiSecret?: string;
  apiFolder?: string;
}

export type ModelCapability =
  | "llm"
  | "vision_llm"
  | "image"
  | "video"
  | "audio"
  | "embedding"
  | "unknown";

export interface NewApiConnectionConfig {
  baseUrl: string;
  apiKeyPreview: string;
  configured: boolean;
}

export interface NewApiCatalogStatus {
  lastTestAt?: string;
  lastSyncAt?: string;
  lastError?: string;
  runtimeRevision?: number;
  restartRequiredComponents?: string[];
  desiredRevision?: number;
  activeRevision?: number | null;
  runtimeState?: "uninitialized" | "pending" | "ready" | "draining" | "applying" | "failed";
  activeLeaseCount?: number;
  lastAppliedAt?: string | null;
  lastReloadError?: string;
}

export interface CatalogModel {
  id: string;
  bindingId: string;
  sourceId: string;
  ownedBy: string;
  capabilities: ModelCapability[];
  inferredCapabilities: ModelCapability[];
  manualCapabilities: ModelCapability[];
  available: boolean;
}

export interface ModelFeature {
  id: string;
  label: string;
  capability: ModelCapability;
  required: boolean;
}

export interface ModelSource {
  id: string;
  name: string;
  type: "newapi" | "openai_compatible";
  baseUrl: string;
  apiKeyPreview: string;
  configured: boolean;
  isDefault: boolean;
}

export interface SaveModelSourceInput {
  id?: string;
  name: string;
  baseUrl: string;
  apiKey?: string;
}

export interface ModelGatewayConfig {
  connection: NewApiConnectionConfig;
  sources: ModelSource[];
  catalogStatus: NewApiCatalogStatus;
  mediaRelay?: MediaRelayConfig;
  officialServiceUrl: string;
  officialServiceLabel: string;
}

export function useModelGatewayConfig(enabled = true) {
  return useQuery({
    queryKey: queryKeys.modelGateway(),
    queryFn: ({ signal }) =>
      api
        .get("api/v1/model-gateway/config", { signal })
        .json<OkResponse<ModelGatewayConfig>>(),
    enabled,
  });
}

export function useSaveMediaRelayConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SaveMediaRelayConfigInput) =>
      api
        .post("api/v1/model-gateway/media-relay/config", {
          json: input,
          timeout: 60_000,
        })
        .json<OkResponse<MediaRelayConfig> | ErrorResponse>(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.modelGateway() });
    },
  });
}

export function useCatalogModels(enabled = true) {
  return useQuery({
    queryKey: ["model-gateway", "models"],
    queryFn: ({ signal }) =>
      api
        .get("api/v1/model-gateway/models", { signal })
        .json<OkResponse<{ models: CatalogModel[]; status: NewApiCatalogStatus }>>(),
    enabled,
  });
}

export function useModelFeatures(enabled = true) {
  return useQuery({
    queryKey: ["model-gateway", "features"],
    queryFn: ({ signal }) =>
      api
        .get("api/v1/model-gateway/features", { signal })
        .json<OkResponse<{ features: ModelFeature[] }>>(),
    enabled,
  });
}

export function useFeatureBindings(enabled = true) {
  return useQuery({
    queryKey: ["model-gateway", "feature-bindings"],
    queryFn: ({ signal }) =>
      api
        .get("api/v1/model-gateway/feature-bindings", { signal })
        .json<OkResponse<{ bindings: Record<string, string> }>>(),
    enabled,
  });
}

export function useSaveNewApiConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { baseUrl: string; apiKey?: string }) =>
      api
        .put("api/v1/model-gateway/connection", { json: input })
        .json<OkResponse<ModelGatewayConfig> | ErrorResponse>(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useTestNewApiConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api
        .post("api/v1/model-gateway/connection/test", { timeout: 30_000 })
        .json<
          | OkResponse<{ connected: boolean; modelCount: number; testedAt: string }>
          | ErrorResponse
        >(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useSyncCatalogModels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api
        .post("api/v1/model-gateway/models/sync", { timeout: 30_000 })
        .json<OkResponse<{ models: CatalogModel[]; syncedAt: string }> | ErrorResponse>(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useSaveFeatureBindings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bindings: Record<string, string | null>) =>
      api
        .put("api/v1/model-gateway/feature-bindings", { json: { bindings } })
        .json<OkResponse<{ bindings: Record<string, string> }> | ErrorResponse>(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useUpdateModelCapabilities() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { modelId: string; capabilities: ModelCapability[] }) =>
      api
        .patch(`api/v1/model-gateway/models/${encodeURIComponent(input.modelId)}`, {
          json: { capabilities: input.capabilities },
        })
        .json<OkResponse<CatalogModel> | ErrorResponse>(),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["model-gateway", "models"] }),
  });
}

export function useTestFeatureModel() {
  return useMutation({
    mutationFn: (featureId: string) =>
      api
        .post(`api/v1/model-gateway/features/${encodeURIComponent(featureId)}/test`, {
          timeout: 30_000,
        })
        .json<
          | OkResponse<{
              featureId: string;
              modelId: string;
              validated: boolean;
              liveRequest: boolean;
            }>
          | ErrorResponse
        >(),
  });
}

export function useModelSources(enabled = true) {
  return useQuery({
    queryKey: ["model-gateway", "sources"],
    queryFn: ({ signal }) => api.get("api/v1/model-gateway/sources", { signal }).json<OkResponse<{ sources: ModelSource[] }>>(),
    enabled,
  });
}

export function useSaveModelSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SaveModelSourceInput) => {
      const payload = { name: input.name, baseUrl: input.baseUrl, ...(input.apiKey ? { apiKey: input.apiKey } : {}) };
      return (input.id
        ? api.put("api/v1/model-gateway/sources/" + encodeURIComponent(input.id), { json: payload })
        : api.post("api/v1/model-gateway/sources", { json: payload })
      ).json<OkResponse<ModelSource> | ErrorResponse>();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useDeleteModelSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => api.delete("api/v1/model-gateway/sources/" + encodeURIComponent(sourceId)).json<OkResponse<{ deleted: boolean }> | ErrorResponse>(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}

export function useTestModelSource() {
  return useMutation({
    mutationFn: (sourceId: string) => api.post("api/v1/model-gateway/sources/" + encodeURIComponent(sourceId) + "/test", { timeout: 30_000 }).json<OkResponse<{ connected: boolean; modelCount: number }> | ErrorResponse>(),
  });
}

export function useSyncModelSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => api.post("api/v1/model-gateway/sources/" + encodeURIComponent(sourceId) + "/models/sync", { timeout: 30_000 }).json<OkResponse<{ models: CatalogModel[]; sourceId: string }> | ErrorResponse>(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["model-gateway"] }),
  });
}
