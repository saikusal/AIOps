type PagePlaceholderProps = {
  title: string;
  description: string;
  endpoints: string[];
};

export function PagePlaceholder({ title, description, endpoints }: PagePlaceholderProps) {
  return (
    <section className="page-card">
      <div className="eyebrow">Migration Target</div>
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="page-card__meta">
        {endpoints.map((endpoint) => (
          <code key={endpoint}>{endpoint}</code>
        ))}
      </div>
    </section>
  );
}
