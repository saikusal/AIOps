type HeroCardProps = {
  title: string;
  summary: string;
  points: string[];
};

export function HeroCard({ title, summary, points }: HeroCardProps) {
  return (
    <section className="hero-card">
      <div className="eyebrow">Vision</div>
      <h2>{title}</h2>
      <p>{summary}</p>
      <div className="hero-card__grid">
        {points.map((point) => (
          <div key={point} className="hero-card__chip">
            {point}
          </div>
        ))}
      </div>
    </section>
  );
}
