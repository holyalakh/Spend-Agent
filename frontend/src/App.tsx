import { AuthProvider, useAuth } from "./hooks/useAuth";
import { ChatProvider } from "./hooks/useChat";
import { AuthScreen } from "./components/AuthScreen";
import { ChatLayout } from "./components/ChatLayout";

function AppContent() {
  const { isAuthenticated, isLoading, challenge } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-cursor-border border-t-cursor-accent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthScreen challenge={challenge} />;
  }

  return (
    <ChatProvider>
      <ChatLayout />
    </ChatProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
