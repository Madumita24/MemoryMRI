"use client";

import { useMemo, useState } from "react";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import { apiClient, ApiClientError } from "@/lib/api/client";
import type {
  BenchmarkExplorerEvidence,
  BenchmarkScenarioRow,
  BenchmarkSourceEvidence,
} from "@/lib/benchmark-shared";
import { getDomainLabel, toSentenceCase } from "@/lib/benchmark-shared";
import { getPublicEnvResult } from "@/lib/env";

type ResultFilter = "all" | "passed" | "failed";
type InvestigationFilter = "all" | "investigated" | "not_investigated";
type SourceKey = keyof BenchmarkExplorerEvidence["sources"];

function verdictTone(value: string | null) {
  if (!value) {
    return "neutral" as const;
  }

  if (value.includes("VERIFIED")) {
    return "success" as const;
  }

  if (value.includes("NOT_APPLICABLE")) {
    return "warning" as const;
  }

  if (value.includes("INCONCLUSIVE")) {
    return "inconclusive" as const;
  }

  return "concern" as const;
}

function getSelectedSource(
  searchParams: URLSearchParams,
  fallback: SourceKey,
): SourceKey {
  const source = searchParams.get("source");
  return source === "fake" ? "fake" : fallback;
}

function filterRows(
  rows: BenchmarkScenarioRow[],
  options: {
    domain: string;
    result: ResultFilter;
    investigation: InvestigationFilter;
    verdict: string;
    runner: string;
    query: string;
  },
) {
  const query = options.query.trim().toLowerCase();

  return rows.filter((row) => {
    if (options.domain !== "all" && row.domain !== options.domain) {
      return false;
    }

    if (options.result === "passed" && !row.passed) {
      return false;
    }

    if (options.result === "failed" && row.passed) {
      return false;
    }

    if (options.investigation === "investigated" && row.investigationStatus !== "investigated") {
      return false;
    }

    if (
      options.investigation === "not_investigated" &&
      row.investigationStatus !== "not investigated"
    ) {
      return false;
    }

    if (options.verdict !== "all" && row.verificationVerdict !== options.verdict) {
      return false;
    }

    if (options.runner !== "all" && row.runnerLabel !== options.runner) {
      return false;
    }

    if (!query) {
      return true;
    }

    const haystack = [
      row.scenarioId,
      row.title,
      row.actualAction,
      row.expectedAction,
      row.failureCategory ?? "",
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(query);
  });
}

export function BenchmarkExplorer({ data }: { data: BenchmarkExplorerEvidence }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const envResult = getPublicEnvResult();
  const [domain, setDomain] = useState("all");
  const [result, setResult] = useState<ResultFilter>("all");
  const [investigation, setInvestigation] = useState<InvestigationFilter>("all");
  const [verdict, setVerdict] = useState("all");
  const [runner, setRunner] = useState("all");
  const [query, setQuery] = useState("");
  const [showEvaluationDetails, setShowEvaluationDetails] = useState(false);
  const [runState, setRunState] = useState<{
    status: "idle" | "running" | "completed" | "error";
    message: string | null;
  }>({ status: "idle", message: null });

  const selectedSourceKey = getSelectedSource(searchParams, "gpt");
  const selectedSource = data.sources[selectedSourceKey];
  const alternateSource = selectedSourceKey === "gpt" ? data.sources.fake : data.sources.gpt;

  const filteredRows = useMemo(
    () =>
      filterRows(selectedSource.scenarioRows, {
        domain,
        result,
        investigation,
        verdict,
        runner,
        query,
      }),
    [domain, investigation, query, result, runner, selectedSource.scenarioRows, verdict],
  );

  const verificationOptions = useMemo(
    () =>
      Array.from(
        new Set(selectedSource.scenarioRows.map((row) => row.verificationVerdict).filter(Boolean)),
      ) as string[],
    [selectedSource.scenarioRows],
  );

  const updateSourceInUrl = (source: SourceKey) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("source", source);
    router.replace(`${pathname}?${params.toString()}`);
  };

  const handleRunBenchmark = async () => {
    const liveRunsEnabled = envResult.ok && envResult.value.enableLiveRuns;
    if (!liveRunsEnabled) {
      return;
    }

    if (selectedSourceKey === "gpt") {
      const confirmed = window.confirm(
        "Run the full official GPT benchmark now? This triggers paid GPT-5.6 calls and the frozen 28/30 baseline will remain the default reference.",
      );
      if (!confirmed) {
        return;
      }
    }

    setRunState({
      status: "running",
      message:
        selectedSourceKey === "gpt"
          ? "Running GPT benchmark with a blocking live request. Cache is disabled in the frozen official baseline, so this may incur API cost."
          : "Running deterministic benchmark with a blocking live request.",
    });

    try {
      const response = await apiClient.runBenchmark({
        runner: selectedSourceKey === "gpt" ? "openai" : "fake",
      });
      const summary = response.summary;
      const passed =
        (isRecord(summary) && typeof summary.passed_scenarios === "number" && summary.passed_scenarios) ||
        (isRecord(summary) &&
          isRecord(summary.overall) &&
          typeof summary.overall.passed_scenarios === "number" &&
          summary.overall.passed_scenarios) ||
        null;
      const total =
        (isRecord(summary) && typeof summary.total_scenarios === "number" && summary.total_scenarios) ||
        (isRecord(summary) &&
          isRecord(summary.overall) &&
          typeof summary.overall.attempted_scenarios === "number" &&
          summary.overall.attempted_scenarios) ||
        null;

      setRunState({
        status: "completed",
        message:
          passed !== null && total !== null
            ? `Completed ${selectedSourceKey} benchmark run: ${passed}/${total}.`
            : `Completed ${selectedSourceKey} benchmark run.`,
      });
    } catch (error) {
      const message =
        error instanceof ApiClientError ? error.message : "Benchmark execution failed.";
      setRunState({
        status: "error",
        message,
      });
    }
  };

  const liveRunsEnabled = envResult.ok && envResult.value.enableLiveRuns;

  return (
    <>
      <PageHeader
        title="Benchmarks"
        description="Frozen benchmark evidence for all 30 scenarios, with explicit runner separation between the official GPT baseline and the deterministic regression baseline."
      />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <SectionCard title="Source Selector" eyebrow="Frozen evidence">
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => updateSourceInUrl("gpt")}
                className={`rounded-full border px-4 py-2 text-sm transition ${
                  selectedSourceKey === "gpt"
                    ? "border-signal-success/40 bg-signal-success/12 text-signal-success"
                    : "border-white/10 text-ink-200 hover:border-white/20 hover:bg-white/[0.04]"
                }`}
              >
                Official GPT baseline
              </button>
              <button
                type="button"
                onClick={() => updateSourceInUrl("fake")}
                className={`rounded-full border px-4 py-2 text-sm transition ${
                  selectedSourceKey === "fake"
                    ? "border-signal-info/40 bg-signal-info/12 text-signal-info"
                    : "border-white/10 text-ink-200 hover:border-white/20 hover:bg-white/[0.04]"
                }`}
              >
                Deterministic fake baseline
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Selected source</p>
                <p className="mt-2 text-xl font-semibold text-ink-50">{selectedSource.label}</p>
                <p className="mt-2 text-sm text-ink-200">
                  {selectedSource.runnerType}
                  {selectedSource.model ? ` • ${selectedSource.model}` : ""}
                </p>
                <p className="mt-1 text-sm text-ink-200">Prompt version: {selectedSource.promptVersion}</p>
                <p className="mt-1 text-sm text-ink-200 break-all">
                  Artifact source: {selectedSource.artifactSource}
                </p>
                <div className="mt-2 text-sm text-ink-100">
                  <Timestamp value={selectedSource.timestamp} />
                </div>
              </div>
              <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Runner separation</p>
                <p className="mt-2 text-sm text-ink-200">
                  This page never mixes GPT and FakeAgentRunner results in one table. Switch sources
                  to compare preserved evidence instead of blending metrics.
                </p>
                <p className="mt-2 text-sm text-ink-200">
                  Alternate source: {alternateSource.label} ({alternateSource.overall.passed}/{alternateSource.overall.attempted})
                </p>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Run Benchmark" eyebrow="Live execution">
          {liveRunsEnabled ? (
            <div className="space-y-4">
              <p className="text-sm leading-6 text-ink-200">
                Live runs are enabled. Runner: <span className="font-mono text-ink-100">{selectedSource.runnerType}</span>.
                {selectedSourceKey === "gpt"
                  ? " GPT runs call the paid model, may incur API usage, and should be intentionally confirmed."
                  : " The deterministic runner is intended for repeatable local regression checks."}
              </p>
              <p className="text-sm text-ink-200">
                Cache behavior: the official frozen GPT artifact was captured with cache disabled, so rerunning it may create new paid calls.
              </p>
              <button
                type="button"
                onClick={() => void handleRunBenchmark()}
                disabled={runState.status === "running"}
                className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {runState.status === "running" ? "Running benchmark..." : "Run benchmark"}
              </button>
              {runState.message ? (
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-3 text-sm text-ink-200">
                  {runState.message}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-3 text-sm leading-6 text-ink-200">
              <p>Live benchmark execution is disabled for the demo frontend.</p>
              <p>
                The default view shows preserved evidence only and does not automatically rerun the full 30-case GPT benchmark.
              </p>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Filters" eyebrow="Scenario explorer">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <label className="space-y-2 text-sm text-ink-200">
            <span>Domain</span>
            <select
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100"
            >
              <option value="all">All domains</option>
              <option value="customer_support">Customer Support</option>
              <option value="devops">DevOps Deployment</option>
              <option value="workplace_expense">Workplace Expense</option>
            </select>
          </label>

          <label className="space-y-2 text-sm text-ink-200">
            <span>Result</span>
            <select
              value={result}
              onChange={(event) => setResult(event.target.value as ResultFilter)}
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100"
            >
              <option value="all">All results</option>
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
            </select>
          </label>

          <label className="space-y-2 text-sm text-ink-200">
            <span>Investigation</span>
            <select
              value={investigation}
              onChange={(event) => setInvestigation(event.target.value as InvestigationFilter)}
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100"
            >
              <option value="all">All investigation states</option>
              <option value="investigated">Investigated</option>
              <option value="not_investigated">Not investigated</option>
            </select>
          </label>

          <label className="space-y-2 text-sm text-ink-200">
            <span>Verification verdict</span>
            <select
              value={verdict}
              onChange={(event) => setVerdict(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100"
            >
              <option value="all">All verdicts</option>
              {verificationOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm text-ink-200">
            <span>Runner type</span>
            <select
              value={runner}
              onChange={(event) => setRunner(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100"
            >
              <option value="all">All runners</option>
              <option value="GPT-5.6">GPT-5.6</option>
              <option value="FakeAgentRunner">FakeAgentRunner</option>
            </select>
          </label>

          <label className="space-y-2 text-sm text-ink-200">
            <span>Search</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Scenario ID, title, or action"
              className="w-full rounded-lg border border-white/10 bg-surface-950/80 px-3 py-2 text-ink-100 placeholder:text-ink-400"
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setShowEvaluationDetails((value) => !value)}
            className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
          >
            {showEvaluationDetails ? "Hide evaluation details" : "Show evaluation details"}
          </button>
          <StatusBadge
            label={showEvaluationDetails ? "expected actions visible" : "expected actions hidden"}
            tone={showEvaluationDetails ? "warning" : "success"}
          />
          <StatusBadge
            label={showEvaluationDetails ? "failure categories visible" : "failure categories hidden"}
            tone={showEvaluationDetails ? "warning" : "success"}
          />
        </div>
      </SectionCard>

      <SectionCard title="Scenario Results" eyebrow={`${selectedSource.scenarioRows.length} preserved rows`}>
        {filteredRows.length === 0 ? (
          <EmptyState
            title="No scenarios match the current filters"
            description="Try clearing a filter, switching runners, or broadening the text search."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-3 text-left text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-[0.22em] text-ink-300">
                  <th className="pb-2 pr-4">Scenario</th>
                  <th className="pb-2 pr-4">Domain</th>
                  <th className="pb-2 pr-4">Title</th>
                  <th className="pb-2 pr-4">Runner</th>
                  <th className="pb-2 pr-4">Actual action</th>
                  {showEvaluationDetails ? <th className="pb-2 pr-4">Expected action</th> : null}
                  <th className="pb-2 pr-4">Result</th>
                  <th className="pb-2 pr-4">Memory count</th>
                  <th className="pb-2 pr-4">Investigation</th>
                  <th className="pb-2 pr-4">Verification</th>
                  {showEvaluationDetails ? <th className="pb-2 pr-4">Failure category</th> : null}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr
                    key={`${selectedSource.key}-${row.scenarioId}`}
                    className="rounded-xl bg-surface-950/70 text-ink-100"
                  >
                    <td className="rounded-l-xl border-y border-l border-white/8 px-4 py-4 font-mono">
                      <Link
                        href={`/benchmarks/${row.scenarioId}?source=${selectedSource.key}&trace=${row.traceId}`}
                        className="transition hover:text-ink-50 hover:underline"
                      >
                        {row.scenarioId}
                      </Link>
                    </td>
                    <td className="border-y border-white/8 px-4 py-4">{getDomainLabel(row.domain)}</td>
                    <td className="border-y border-white/8 px-4 py-4">
                      <Link
                        href={`/benchmarks/${row.scenarioId}?source=${selectedSource.key}&trace=${row.traceId}`}
                        className="transition hover:text-ink-50 hover:underline"
                      >
                        {row.title}
                      </Link>
                    </td>
                    <td className="border-y border-white/8 px-4 py-4">{row.runnerLabel}</td>
                    <td className="border-y border-white/8 px-4 py-4 font-mono">{row.actualAction}</td>
                    {showEvaluationDetails ? (
                      <td className="border-y border-white/8 px-4 py-4 font-mono">{row.expectedAction}</td>
                    ) : null}
                    <td className="border-y border-white/8 px-4 py-4">
                      <StatusBadge label={row.passed ? "pass" : "fail"} tone={row.passed ? "success" : "failure"} />
                    </td>
                    <td className="border-y border-white/8 px-4 py-4">{row.memoryCount}</td>
                    <td className="border-y border-white/8 px-4 py-4">
                      <div className="space-y-1">
                        <StatusBadge
                          label={row.investigationStatus}
                          tone={row.investigationStatus === "investigated" ? "info" : "neutral"}
                        />
                        {row.investigationId ? (
                          <p className="font-mono text-xs text-ink-300">{row.investigationId}</p>
                        ) : null}
                      </div>
                    </td>
                    <td className="border-y border-white/8 px-4 py-4">
                      <div className="space-y-1">
                        <StatusBadge
                          label={row.verificationVerdict ?? "not reviewed"}
                          tone={verdictTone(row.verificationVerdict)}
                        />
                        {row.artifactId ? (
                          <p className="font-mono text-xs text-ink-300">{row.artifactId}</p>
                        ) : null}
                      </div>
                    </td>
                    {showEvaluationDetails ? (
                      <td className="rounded-r-xl border-y border-r border-white/8 px-4 py-4">
                        {row.failureCategory ? toSentenceCase(row.failureCategory) : "n/a in this source"}
                      </td>
                    ) : (
                      <td className="rounded-r-xl border-y border-r border-white/8 px-4 py-4 hidden" />
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
