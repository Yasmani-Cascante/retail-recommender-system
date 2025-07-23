import { useEffect, useRef } from 'react';
import { clsx } from 'clsx';
import type { Message } from '../types/widget';
import { ProductCard } from './ProductCard';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

export function MessageList({ messages, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="rr-flex-1 rr-overflow-y-auto rr-p-4 rr-space-y-4">
      {messages.map((message) => (
        <div
          key={message.id}
          className={clsx(
            'rr-flex',
            message.type === 'user' ? 'rr-justify-end' : 'rr-justify-start'
          )}
        >
          <div
            className={clsx(
              'rr-max-w-xs lg:rr-max-w-md rr-px-4 rr-py-2 rr-rounded-lg rr-animate-slide-up',
              message.type === 'user'
                ? 'rr-bg-primary-600 rr-text-white'
                : message.type === 'error'
                ? 'rr-bg-red-100 rr-text-red-800 rr-border rr-border-red-300'
                : 'rr-bg-gray-100 rr-text-gray-800'
            )}
          >
            <p className="rr-text-sm rr-whitespace-pre-wrap">{message.content}</p>
            
            {/* Show recommendations for assistant messages */}
            {message.recommendations && message.recommendations.length > 0 && (
              <div className="rr-mt-3 rr-space-y-2">
                <p className="rr-text-xs rr-font-semibold rr-text-gray-600">
                  Recommended for you:
                </p>
                <div className="rr-space-y-2">
                  {message.recommendations.slice(0, 3).map((product) => (
                    <ProductCard key={product.id} product={product} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ))}
      
      {/* Loading indicator */}
      {isLoading && (
        <div className="rr-flex rr-justify-start">
          <div className="rr-bg-gray-100 rr-px-4 rr-py-2 rr-rounded-lg">
            <div className="rr-flex rr-space-x-1">
              <div 
                className="rr-w-2 rr-h-2 rr-bg-gray-400 rr-rounded-full rr-animate-bounce"
              ></div>
              <div 
                className="rr-w-2 rr-h-2 rr-bg-gray-400 rr-rounded-full rr-animate-bounce"
                style={{ animationDelay: '0.1s' }}
              ></div>
              <div 
                className="rr-w-2 rr-h-2 rr-bg-gray-400 rr-rounded-full rr-animate-bounce"
                style={{ animationDelay: '0.2s' }}
              ></div>
            </div>
          </div>
        </div>
      )}
      
      <div ref={messagesEndRef} />
    </div>
  );
}