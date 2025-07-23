import React, { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

interface MessageInputProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({ 
  onSendMessage, 
  disabled = false, 
  placeholder = "Ask me anything about products..." 
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (message.trim() && !disabled) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  return (
    <form onSubmit={handleSubmit} className="rr-border-t rr-border-gray-200 rr-p-4">
      <div className="rr-flex rr-items-end rr-space-x-2">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="rr-flex-1 rr-resize-none rr-border rr-border-gray-300 rr-rounded-lg rr-px-3 rr-py-2 rr-text-sm focus:rr-outline-none focus:rr-ring-2 focus:rr-ring-primary-500 focus:rr-border-transparent disabled:rr-bg-gray-100 disabled:rr-cursor-not-allowed rr-max-h-32"
        />
        
        <button
          type="submit"
          disabled={!message.trim() || disabled}
          className="rr-bg-primary-600 rr-text-white rr-p-2 rr-rounded-lg disabled:rr-bg-gray-300 disabled:rr-cursor-not-allowed hover:rr-bg-primary-700 rr-transition-colors"
        >
          <Send size={16} />
        </button>
      </div>
    </form>
  );
}