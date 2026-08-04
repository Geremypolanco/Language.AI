import { useState } from 'react';
import { ConsentProvider } from './context/ConsentContext.jsx';
import CookieConsentBanner from './components/CookieConsentBanner.jsx';
import ChatWindow from './components/ChatWindow.jsx';
import VoiceCallScreen from './components/VoiceConversation/VoiceCallScreen.jsx';
import './App.css';

export default function App() {
  const [view, setView] = useState('voice');

  return (
    <ConsentProvider>
      <main>
        <nav className="view-switch" aria-label="Modo de conversación">
          <button
            type="button"
            className={view === 'voice' ? 'view-switch__btn view-switch__btn--active' : 'view-switch__btn'}
            onClick={() => setView('voice')}
          >
            🎙️ Voz
          </button>
          <button
            type="button"
            className={view === 'text' ? 'view-switch__btn view-switch__btn--active' : 'view-switch__btn'}
            onClick={() => setView('text')}
          >
            💬 Texto
          </button>
        </nav>
        {view === 'voice' ? <VoiceCallScreen /> : <ChatWindow />}
      </main>
      <CookieConsentBanner />
    </ConsentProvider>
  );
}
