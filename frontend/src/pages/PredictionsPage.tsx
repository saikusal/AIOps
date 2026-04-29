import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRecentPredictions } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function scoreLabel(score: number) {
  if (score >= 0.75) return "High";
  if (score >= 0.45) return "Medium";
  return "Low";
}

export function PredictionsPage() {
  const refreshQueryOptions = useRefreshQueryOptions();
  const predictionsQuery = useQuery({
    queryKey: ["recent-predictions"],
    queryFn: fetchRecentPredictions,
    ...refreshQueryOptions,
  });

  return (
    <>
      <section className="hero-card hero-card--predictions">
        <div className="eyebrow">Prediction Center</div>
        <h2>Risk Forecast</h2>
        <p>
          Track which services are most likely to degrade next and investigate predictive risk before incidents spread.
        </p>
      </section>

      {predictionsQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching prediction data</h2>
          <p>The frontend is waiting on `/genai/predictions/recent/`.</p>
        </section>
      ) : predictionsQuery.isError ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Prediction feed unavailable</h2>
          <p>The frontend could not load `/genai/predictions/recent/`.</p>
        </section>
      ) : (
        <section className="prediction-grid">
          {(predictionsQuery.data || []).map((prediction) => (
            <article key={`${prediction.application}-${prediction.service}-${prediction.created_at}`} className={`prediction-card prediction-card--${scoreLabel(prediction.risk_score).toLowerCase()}`}>
              <div className="prediction-card__top">
                <div>
                  <div className="eyebrow">{prediction.application}</div>
                  <h3>{prediction.service}</h3>
                </div>
                <div className={`app-portfolio__status app-portfolio__status--${scoreLabel(prediction.risk_score).toLowerCase() === "high" ? "down" : scoreLabel(prediction.risk_score).toLowerCase() === "medium" ? "degraded" : "healthy"}`}>
                  {scoreLabel(prediction.risk_score)}
                </div>
              </div>
              <div className="prediction-card__score">
                <strong>{Math.round(prediction.risk_score * 100)}%</strong>
                <span>risk in next {prediction.predicted_window_minutes}m</span>
              </div>
              <p>{prediction.explanation || "No explanation available yet."}</p>
              <div className="page-card__meta">
                {(prediction.blast_radius || []).map((item) => (
                  <code key={`${prediction.service}-${item}`}>{item}</code>
                ))}
              </div>
              <div className="page-card__meta">
                <Link
                  className="shell__link shell__link--small"
                  to={`/genai?application=${encodeURIComponent(prediction.application)}&service=${encodeURIComponent(prediction.service)}`}
                >
                  Ask Assistant Why
                </Link>
                <Link className="shell__link shell__link--small" to={`/incidents?service=${encodeURIComponent(prediction.service)}`}>
                  Related Incidents
                </Link>
                <Link className="shell__link shell__link--small" to={`/graph/application/${encodeURIComponent(prediction.application)}`}>
                  App Graph
                </Link>
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
