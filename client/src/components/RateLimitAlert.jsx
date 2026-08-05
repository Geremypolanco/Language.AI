import './RateLimitAlert.css';

export default function RateLimitAlert({ secondsRemaining }) {
  if (secondsRemaining <= 0) return null;

  return (
    <div className="rate-limit-alert" role="alert">
      <span className="rate-limit-alert__icon" aria-hidden="true">
        ⏳
      </span>
      Has alcanzado el límite de solicitudes a la IA. Podrás volver a intentarlo en <strong>{secondsRemaining}s</strong>
      .
    </div>
  );
}
