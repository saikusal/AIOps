import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchChatSessions,
  initChatSession,
  resetChatSession,
  sendChatMessage,
  type ChatReply,
  type ChatMessage,
} from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

type RcaMeta = {
  confidence?: string;
  confidence_reason?: string;
  decision_policy?: string;
  hard_evidence?: string[];
  missing_evidence?: string[];
  supporting_evidence?: string[];
  contradicting_evidence?: string[];
  next_verification_step?: string;
  target_host?: string;
  business_impact?: Record<string, unknown>;
  code_context?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
};

function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function safeList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry)) : [];
}

function formatCurrency(value: unknown, currency = "INR") {
  const numeric = typeof value === "number" ? value : Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(numeric);
}

function CodeContextPanel({ meta }: { meta: RcaMeta }) {
  const codeContext = safeRecord(meta.code_context);
  const owner = safeRecord(codeContext.owner);
  const routeBinding = safeRecord(codeContext.route_binding);
  const spanBinding = safeRecord(codeContext.span_binding);
  const blastRadius = safeRecord(safeRecord(codeContext.blast_radius).blast_radius);
  const snippets = safeList(codeContext.snippets);
  const recentChanges = safeList(safeRecord(codeContext.recent_changes).recent_changes);
  const searchMatches = safeList(safeRecord(codeContext.search_context).matches);
  const retrieval = safeRecord(meta.retrieval);
  const toolCalls = Array.isArray(retrieval.tool_calls) ? retrieval.tool_calls.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object") : [];
  const businessImpact = safeRecord(meta.business_impact);

  if (!Object.keys(codeContext).length && !Object.keys(businessImpact).length) {
    return null;
  }

  return (
    <div className="assistant-code-context">
      <div className="assistant-code-context__header">
        <span className="assistant-code-context__badge">CODE-AWARE INVESTIGATION</span>
        {owner.repository ? (
          <div className="assistant-code-context__links">
            <Link className="shell__link shell__link--small" to={`/code-context?repository=${encodeURIComponent(String(owner.repository))}`}>
              Open Code Graph
            </Link>
            {typeof owner.application_name === "string" && owner.application_name ? (
              <Link className="shell__link shell__link--small" to={`/topology`}>
                Open Topology
              </Link>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="assistant-code-context__grid">
        <div className="assistant-code-context__card">
          <span>Repository</span>
          <strong>{String(owner.repository || "—")}</strong>
          <small>{String(owner.repository_path || routeBinding.module_path || spanBinding.module_path || "No repository mapping yet.")}</small>
        </div>
        <div className="assistant-code-context__card">
          <span>Handler / Symbol</span>
          <strong>{String(routeBinding.handler || spanBinding.symbol || "—")}</strong>
          <small>{String(routeBinding.route || spanBinding.span_name || "No route/span binding yet.")}</small>
        </div>
        <div className="assistant-code-context__card">
          <span>Blast Radius</span>
          <strong>{String(blastRadius.risk_level || "—")}</strong>
          <small>{typeof blastRadius.affected_symbol_count === "number" ? `${blastRadius.affected_symbol_count} related symbols` : "No code blast-radius estimate yet."}</small>
        </div>
        <div className="assistant-code-context__card">
          <span>Business Impact</span>
          <strong>
            {Object.keys(businessImpact).length
              ? formatCurrency(businessImpact.current_estimated_revenue_lost ?? businessImpact.revenue_lost, String(businessImpact.currency || "INR"))
              : "—"}
          </strong>
          <small>{String(businessImpact.impact_level || businessImpact.data_source || "No quantified business impact yet.")}</small>
        </div>
      </div>

      {recentChanges.length > 0 ? (
        <div className="assistant-code-context__section">
          <span>Recent Changes On The Failure Path</span>
          <ul>
            {recentChanges.slice(0, 3).map((change, index) => (
              <li key={`change-${index}`}>
                <strong>{String(change.commit_sha || "").slice(0, 7) || "change"}</strong>
                <span>{String(change.title || "Untitled change")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {searchMatches.length > 0 ? (
        <div className="assistant-code-context__section">
          <span>Relevant Modules</span>
          <ul>
            {searchMatches.slice(0, 3).map((match, index) => (
              <li key={`match-${index}`}>
                <strong>{String(match.label || match.symbol || "module")}</strong>
                <span>{String(match.module_path || "unknown path")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {snippets.length > 0 ? (
        <div className="assistant-code-context__section">
          <span>Snippet Evidence</span>
          {snippets.slice(0, 2).map((snippet, index) => (
            <article key={`snippet-${index}`} className="assistant-code-context__snippet">
              <strong>{String(snippet.module_path || snippet.symbol || "code snippet")}</strong>
              <pre>{String(snippet.snippet || "")}</pre>
            </article>
          ))}
        </div>
      ) : null}

      {toolCalls.length > 0 ? (
        <div className="assistant-code-context__trace">
          <span>Retrieval Trace</span>
          <div className="assistant-code-context__trace-list">
            {toolCalls.slice(0, 8).map((tool, index) => (
              <code key={`tool-${index}`}>
                {String(tool.tool_name || "tool")} · {String(tool.latency_ms || 0)}ms
              </code>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RcaPanel({ meta }: { meta: RcaMeta }) {
  const level = meta.confidence ?? "medium";
  const decisionPolicy = meta.decision_policy ?? "diagnose";
  const confidenceReason = meta.confidence_reason ?? "";
  const hardEvidence = meta.hard_evidence ?? [];
  const missingEvidence = meta.missing_evidence ?? [];
  const supporting = meta.supporting_evidence ?? [];
  const contradicting = meta.contradicting_evidence ?? [];
  const nextStep = meta.next_verification_step ?? "";
  return (
    <div className={`rca-confidence rca-confidence--${level}`}>
      <div className="rca-confidence__header">
        <span className="rca-confidence__badge">{level.toUpperCase()} CONFIDENCE</span>
        <span className={`decision-policy decision-policy--${decisionPolicy}`}>{decisionPolicy.toUpperCase()}</span>
        {nextStep && <span className="rca-confidence__next">Next: {nextStep}</span>}
      </div>
      {confidenceReason && <div className="rca-confidence__reason">{confidenceReason}</div>}
      {hardEvidence.length > 0 && (
        <div className="rca-evidence rca-evidence--hard">
          <span className="rca-evidence__label">Hard Evidence</span>
          <ul>{hardEvidence.map((item, i) => <li key={`hard-${i}`}>{item}</li>)}</ul>
        </div>
      )}
      {missingEvidence.length > 0 && (
        <div className="rca-evidence rca-evidence--missing">
          <span className="rca-evidence__label">Missing Evidence</span>
          <ul>{missingEvidence.map((item, i) => <li key={`missing-${i}`}>{item}</li>)}</ul>
        </div>
      )}
      {supporting.length > 0 && (
        <div className="rca-evidence rca-evidence--supporting">
          <span className="rca-evidence__label">Supporting</span>
          <ul>{supporting.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
      )}
      {contradicting.length > 0 && (
        <div className="rca-evidence rca-evidence--contradicting">
          <span className="rca-evidence__label">Contradicting</span>
          <ul>{contradicting.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function renderMessageContent(content: string) {
  const blocks = content.split("\n").map((line) => line.trim()).filter(Boolean);
  const bulletLines = blocks.filter((line) => line.startsWith("- ") || line.startsWith("* "));
  const plainLines = blocks.filter((line) => !(line.startsWith("- ") || line.startsWith("* ")));

  return (
    <>
      {plainLines.map((line, index) => (
        <p key={`p-${index}`}>{line}</p>
      ))}
      {bulletLines.length ? (
        <ul>
          {bulletLines.map((line, index) => (
            <li key={`b-${index}`}>{line.slice(2)}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

export function AssistantPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const refreshQueryOptions = useRefreshQueryOptions();
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");

  const pinnedApplication = searchParams.get("application") || "";
  const pinnedService = searchParams.get("service") || "";
  const pinnedIncident = searchParams.get("incident") || "";

  const sessionsQuery = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: fetchChatSessions,
    ...refreshQueryOptions,
  });

  const sessionInitQuery = useQuery({
    queryKey: ["chat-session", activeSessionId],
    queryFn: () => initChatSession(activeSessionId),
  });

  useEffect(() => {
    if (sessionInitQuery.data?.messages) {
      setMessages(sessionInitQuery.data.messages);
      if (!activeSessionId && sessionInitQuery.data.session_id) {
        setActiveSessionId(sessionInitQuery.data.session_id);
      }
    }
  }, [sessionInitQuery.data, activeSessionId]);

  useEffect(() => {
    const contextPrompt = [pinnedApplication && `application=${pinnedApplication}`, pinnedService && `service=${pinnedService}`, pinnedIncident && `incident=${pinnedIncident}`]
      .filter(Boolean)
      .join(" | ");

    if (contextPrompt && !messages.length && !draft) {
      setDraft(`Help me investigate ${contextPrompt}. Start with the likely RCA, blast radius, and next diagnostic step.`);
    }
  }, [pinnedApplication, pinnedService, pinnedIncident, messages.length, draft]);

  const sendMutation = useMutation({
    mutationFn: (question: string) =>
      sendChatMessage({
        session_id: activeSessionId,
        question,
      }),
    onMutate: async (question: string) => {
      if (!question.trim()) return;
      setPendingQuestion(question);
      setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: "user",
          content: question,
          created_at: new Date().toISOString(),
          metadata: {},
        },
      ]);
      setDraft("");
    },
    onSuccess: async (payload) => {
      setPendingQuestion("");
      setMessages((current) => [
        ...current,
                {
                  id: Date.now() + 1,
                  role: "assistant",
                  content: payload.answer || "No answer returned.",
                  created_at: new Date().toISOString(),
                  metadata: {
                    follow_up_questions: payload.follow_up_questions,
                    confidence: payload.confidence,
                    confidence_reason: payload.confidence_reason,
                    decision_policy: payload.decision_policy,
                    hard_evidence: payload.hard_evidence,
                    missing_evidence: payload.missing_evidence,
                    supporting_evidence: payload.supporting_evidence,
                    contradicting_evidence: payload.contradicting_evidence,
                    next_verification_step: payload.next_verification_step,
                    target_host: payload.target_host,
                    business_impact: payload.business_impact,
                    code_context: payload.code_context,
                    retrieval: payload.retrieval,
                  },
                },
              ]);
      if (payload.session_id) {
        setActiveSessionId(payload.session_id);
      }
      await queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
    onError: (error) => {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 2,
          role: "assistant",
          content: error instanceof Error ? error.message : "The assistant request failed.",
          created_at: new Date().toISOString(),
          metadata: { error: true },
        },
      ]);
      if (!draft && pendingQuestion) {
        setDraft(pendingQuestion);
      }
      setPendingQuestion("");
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetChatSession(activeSessionId),
    onSuccess: async (payload) => {
      setActiveSessionId(payload.session_id);
      setMessages(payload.messages || []);
      await queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["chat-session"] });
    },
  });

  const sessionSummaries = sessionsQuery.data || [];
  const currentTitle = useMemo(() => {
    return sessionSummaries.find((item) => item.session_id === activeSessionId)?.title || sessionInitQuery.data?.title || "New Investigation";
  }, [sessionSummaries, activeSessionId, sessionInitQuery.data]);

  const suggestedPrompts = useMemo(() => {
    const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");
    const followUps = Array.isArray(latestAssistantMessage?.metadata?.follow_up_questions)
      ? latestAssistantMessage?.metadata?.follow_up_questions
          .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
          .slice(0, 4)
      : [];

    if (followUps.length) {
      return followUps;
    }

    return [
      "Give me the RCA for the active incident.",
      "What is the blast radius if the database fails?",
      "What command should we run next and why?",
      "Summarize the highest-risk service in the next 15 minutes.",
    ];
  }, [messages]);

  function submitPrompt(question: string) {
    const nextQuestion = question.trim();
    if (!nextQuestion || sendMutation.isPending) return;
    sendMutation.mutate(nextQuestion);
  }

  return (
    <>
      <section className="hero-card hero-card--assistant">
        <div className="eyebrow">Full AI Workspace</div>
        <h2>Investigation Copilot</h2>
        <p>
          Ask for RCA, dependency impact, next diagnostics, prediction context, or runbook guidance from a single stateful investigation workspace.
        </p>
        {(pinnedApplication || pinnedService || pinnedIncident) ? (
          <div className="hero-card__grid">
            {pinnedApplication ? <div className="hero-card__chip">Application: {pinnedApplication}</div> : null}
            {pinnedService ? <div className="hero-card__chip">Service: {pinnedService}</div> : null}
            {pinnedIncident ? <div className="hero-card__chip">Incident: {pinnedIncident}</div> : null}
          </div>
        ) : null}
      </section>

      <section className="assistant-layout">
        <aside className="assistant-sidebar">
          <div className="assistant-sidebar__header">
            <div>
              <div className="eyebrow">Conversations</div>
              <h3>History</h3>
            </div>
            <button className="assistant-button assistant-button--secondary" onClick={() => resetMutation.mutate()} disabled={resetMutation.isPending}>
              New Chat
            </button>
          </div>
          <div className="assistant-session-list">
            {sessionSummaries.map((session) => (
              <button
                key={session.session_id}
                className={`assistant-session${session.session_id === activeSessionId ? " is-active" : ""}`}
                onClick={() => setActiveSessionId(session.session_id)}
              >
                <strong>{session.title}</strong>
                <span>{session.last_message_preview || "No messages yet"}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="assistant-chat">
          <div className="assistant-chat__header">
            <div>
              <div className="eyebrow">Active Session</div>
              <h3>{currentTitle}</h3>
            </div>
            <div className="assistant-chat__hint">
              Ask for RCA, blast radius, next diagnostics, predictions, or document-backed procedures.
            </div>
          </div>
          <div className="assistant-chat__messages">
            {messages.map((message) => (
              <article key={`${message.id}-${message.created_at}`} className={`assistant-message assistant-message--${message.role}`}>
                <div className="assistant-message__role">{message.role}</div>
                <div className="assistant-message__content">{renderMessageContent(message.content)}</div>
                {message.role === "assistant" && Boolean(message.metadata?.confidence) && (
                  <>
                    <RcaPanel meta={message.metadata as RcaMeta} />
                    <CodeContextPanel meta={message.metadata as RcaMeta} />
                  </>
                )}
              </article>
            ))}
          </div>
          <div className="assistant-prompts">
            {suggestedPrompts.map((prompt) => (
              <button key={prompt} className="assistant-prompt-chip" onClick={() => submitPrompt(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
          <div className="assistant-chat__composer">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  submitPrompt(draft);
                }
              }}
              placeholder="Ask for RCA, blast radius, next diagnostics, or application health..."
            />
            <button
              className="assistant-button"
              disabled={sendMutation.isPending || !draft.trim()}
              onClick={() => submitPrompt(draft)}
            >
              {sendMutation.isPending ? "Thinking..." : "Send"}
            </button>
          </div>
        </section>
      </section>
    </>
  );
}
