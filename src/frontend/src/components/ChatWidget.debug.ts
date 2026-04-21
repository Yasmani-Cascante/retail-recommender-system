/**
 * Debug script para diagnosticar el comportamiento del header hiding en ChatWidget
 * Agrega esto al ChatWidget.tsx para revisar qué está pasando
 */

export function debugScrollBehavior() {
  console.log('=== DEBUG: Chat Widget Scroll ===');
  
  const container = document.querySelector('.ChatWidget_messagesContainer__') as HTMLElement;
  if (!container) {
    console.error('❌ messagesContainer no encontrado');
    return;
  }

  console.log({
    'containerHeight': container.clientHeight,
    'containerScrollHeight': container.scrollHeight,
    'hasScroll': container.scrollHeight > container.clientHeight,
    'currentScrollTop': container.scrollTop,
    'overflow-y': getComputedStyle(container).overflowY,
  });

  // Simular scroll
  container.addEventListener('scroll', () => {
    console.log('✅ SCROLL EVENT FIRED', {
      scrollTop: container.scrollTop,
      scrollHeight: container.scrollHeight,
      clientHeight: container.clientHeight,
    });
  }, { once: false });

  console.log('📌 Intentando scrollear 100px...');
  container.scrollTop = 100;
}
