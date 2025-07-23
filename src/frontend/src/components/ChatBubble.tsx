import { MessageCircle } from 'lucide-react';
import { clsx } from 'clsx';

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
  className 
}: ChatBubbleProps) {
  // If chat is open and minimized, show minimize button
  if (isOpen && isMinimized) {
    return (
      <div className={clsx(
        'rr-fixed rr-bottom-4 rr-right-4 rr-bg-primary-600 rr-text-white rr-rounded-full rr-p-3 rr-shadow-lg rr-cursor-pointer rr-z-50 rr-transition-all rr-duration-300 hover:rr-bg-primary-700',
        className
      )}>
        <button
          onClick={onToggle}
          className="rr-flex rr-items-center rr-justify-center rr-w-6 rr-h-6"
          title="Expand chat"
        >
          <MessageCircle size={20} />
        </button>
      </div>
    );
  }

  // If chat is open and not minimized, don't show the bubble (the minimize button is in the chat header)
  if (isOpen && !isMinimized) {
    return null;
  }

  // Default state: chat is closed, show main chat bubble
  return (
    <div className={clsx(
      'rr-fixed rr-bottom-4 rr-right-4 rr-bg-primary-600 rr-text-white rr-rounded-full rr-p-4 rr-shadow-lg rr-cursor-pointer rr-z-50 rr-transition-all rr-duration-300 hover:rr-bg-primary-700 hover:rr-scale-110',
      className
    )}>
      <button
        onClick={onToggle}
        className="rr-flex rr-items-center rr-justify-center rr-relative"
        title="Open chat"
      >
        <MessageCircle size={24} />
        {hasUnreadMessages && (
          <div className="rr-absolute -rr-top-1 -rr-right-1 rr-w-3 rr-h-3 rr-bg-red-500 rr-rounded-full rr-animate-pulse"></div>
        )}
      </button>
    </div>
  );
}