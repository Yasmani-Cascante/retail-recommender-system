import styles from './ChatBubble.module.css';

interface ChatBubbleProps {
  isOpen: boolean;
  isMinimized: boolean;
  hasUnreadMessages: boolean;
  onToggle: () => void;
  onMinimize: () => void;
  className?: string;
}

export function ChatBubble({
  isOpen,
  isMinimized,
  hasUnreadMessages,
  onToggle,
}: ChatBubbleProps) {
  // Si el chat está abierto y no minimizado → no mostrar burbuja
  if (isOpen && !isMinimized) return null;

  return (
    <button
      onClick={onToggle}
      className={styles.bubble}
      title={isOpen ? 'Expandir chat' : 'Abrir asistente de moda'}
      aria-label="Abrir asistente de moda"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        width="24"
        height="24"
        fill="none"
      >
        <g clipPath="url(#clip0_990_39490)">
          <path
            d="M13.4733 5H21V18.2102L16.14 22V18.2102H6V12.2941"
            stroke="currentColor"
            strokeWidth="2.03704"
            strokeMiterlimit="10"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M10 5.00002C7.74328 5.00002 6.00049 3.25689 6.00049 1C6.00049 3.25689 4.25672 5.00021 2 5.00021C4.25672 5.00021 5.9997 6.74311 5.9997 9C5.9997 6.74311 7.74328 5.00002 10 5.00002Z"
            stroke="currentColor"
            strokeWidth="2.03704"
            strokeLinejoin="round"
            style={{ transitionProperty: 'transform', transitionDuration: '0.3s', transform: 'scale(1.0)' }}
          />
        </g>
      </svg>
      {/* Badge de mensajes no leídos */}
      {hasUnreadMessages && (
        <span className={styles.badge} aria-hidden="true" />
      )}
    </button>
  );
}
