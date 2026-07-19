"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient, queryKeys } from "./client";

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: apiClient.getHealth,
    refetchInterval: 30000,
    retry: 1,
  });
}

export function useDomainsQuery() {
  return useQuery({
    queryKey: queryKeys.domains,
    queryFn: apiClient.getDomains,
    staleTime: 60000,
    retry: 1,
  });
}

export function useScenariosQuery() {
  return useQuery({
    queryKey: queryKeys.scenarios,
    queryFn: apiClient.getScenarios,
    staleTime: 60000,
    retry: 1,
  });
}

export function useInvestigationQuery(investigationId: string | null) {
  return useQuery({
    queryKey: queryKeys.investigation(investigationId ?? "missing"),
    queryFn: () => apiClient.getInvestigation(investigationId ?? ""),
    enabled: Boolean(investigationId),
    retry: 1,
  });
}

export function useInvestigationResultsQuery(investigationId: string | null) {
  return useQuery({
    queryKey: queryKeys.investigationResults(investigationId ?? "missing"),
    queryFn: () => apiClient.getInvestigationResults(investigationId ?? ""),
    enabled: Boolean(investigationId),
    retry: 1,
  });
}

export function useVerificationQuery(verificationId: string | null) {
  return useQuery({
    queryKey: queryKeys.verification(verificationId ?? "missing"),
    queryFn: () => apiClient.getVerification(verificationId ?? ""),
    enabled: Boolean(verificationId),
    retry: 1,
  });
}

export function useArtifactQuery(artifactId: string | null) {
  return useQuery({
    queryKey: queryKeys.artifact(artifactId ?? "missing"),
    queryFn: () => apiClient.getArtifact(artifactId ?? ""),
    enabled: Boolean(artifactId),
    retry: 1,
  });
}

export function useArtifactMarkdownQuery(artifactId: string | null) {
  return useQuery({
    queryKey: queryKeys.artifactMarkdown(artifactId ?? "missing"),
    queryFn: () => apiClient.getArtifactMarkdown(artifactId ?? ""),
    enabled: Boolean(artifactId),
    retry: 1,
  });
}
