import { ConsentProvider } from './context/ConsentContext.jsx';
import CookieConsentBanner from './components/CookieConsentBanner.jsx';
import ChatWindow from './components/ChatWindow.jsx';

export default function App() {
  return (
    <ConsentProvider>
      <main>
        <ChatWindow />
      </main>
      <CookieConsentBanner />
    </ConsentProvider>
  );
}
