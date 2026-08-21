"use client";

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { Shell } from "./components/Shell";
import { ErrorState, LoadingState } from "./components/ui";
import { api } from "./lib/api";
import { LoginPage } from "./pages/LoginPage";

const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const ClassesPage = lazy(() =>
  import("./pages/ClassesPage").then((module) => ({
    default: module.ClassesPage,
  })),
);
const ClassDetailPage = lazy(() =>
  import("./pages/ClassesPage").then((module) => ({
    default: module.ClassDetailPage,
  })),
);
const MaterialsPage = lazy(() =>
  import("./pages/MaterialsPage").then((module) => ({
    default: module.MaterialsPage,
  })),
);
const MaterialDetailPage = lazy(() =>
  import("./pages/MaterialsPage").then((module) => ({
    default: module.MaterialDetailPage,
  })),
);
const GeneratePage = lazy(() =>
  import("./pages/GeneratePage").then((module) => ({
    default: module.GeneratePage,
  })),
);
const GenerationProgressPage = lazy(() =>
  import("./pages/GeneratePage").then((module) => ({
    default: module.GenerationProgressPage,
  })),
);
const PackagesPage = lazy(() =>
  import("./pages/PackagesPage").then((module) => ({
    default: module.PackagesPage,
  })),
);
const EditorPage = lazy(() =>
  import("./pages/PackagesPage").then((module) => ({
    default: module.EditorPage,
  })),
);
const PreviewPage = lazy(() =>
  import("./pages/PreviewPage").then((module) => ({
    default: module.PreviewPage,
  })),
);
const ExportsPage = lazy(() =>
  import("./pages/ExportsPage").then((module) => ({
    default: module.ExportsPage,
  })),
);
const MembersPage = lazy(() =>
  import("./pages/MembersPage").then((module) => ({
    default: module.MembersPage,
  })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

const subscribeToClientRuntime = () => () => undefined;
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ left: 0, top: 0, behavior: "instant" });
  }, [pathname]);

  return null;
}

function AuthenticatedApp({
  token,
  logout,
  onTokenChange,
}: {
  token: string;
  logout: () => void;
  onTokenChange: (token: string) => void;
}) {
  const user = useQuery({
    queryKey: ["current-user", token],
    queryFn: () => api.me(token),
    retry: false,
  });
  if (user.isLoading)
    return (
      <div className="app-loading">
        <LoadingState label="開啟 LessonForge 工作台…" />
      </div>
    );
  if (user.error || !user.data)
    return (
      <div className="app-loading">
        <ErrorState
          message={
            user.error instanceof Error ? user.error.message : "登入憑證已失效"
          }
          retry={logout}
        />
      </div>
    );
  return (
    <Shell user={user.data} onLogout={logout}>
      <Suspense fallback={<LoadingState label="載入工作區…" />}>
        <Routes>
          <Route path="/" element={<DashboardPage token={token} />} />
          <Route path="/classes" element={<ClassesPage token={token} />} />
          <Route
            path="/classes/:id"
            element={<ClassDetailPage token={token} />}
          />
          <Route path="/materials" element={<MaterialsPage token={token} />} />
          <Route
            path="/materials/:id"
            element={<MaterialDetailPage token={token} />}
          />
          <Route path="/generate" element={<GeneratePage token={token} />} />
          <Route
            path="/generation/:id"
            element={<GenerationProgressPage token={token} />}
          />
          <Route path="/packages" element={<PackagesPage token={token} />} />
          <Route path="/packages/:id" element={<EditorPage token={token} />} />
          <Route
            path="/packages/:id/preview"
            element={<PreviewPage token={token} />}
          />
          <Route path="/exports" element={<ExportsPage token={token} />} />
          <Route
            path="/members"
            element={
              <MembersPage
                token={token}
                currentUser={user.data}
                onTokenChange={onTokenChange}
              />
            }
          />
          <Route path="/settings" element={<SettingsPage token={token} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}

export function LessonForgeApp() {
  const mounted = useSyncExternalStore(
    subscribeToClientRuntime,
    getClientSnapshot,
    getServerSnapshot,
  );
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 20_000, retry: 1 } },
      }),
    [],
  );
  const [token, setToken] = useState(() =>
    typeof window === "undefined"
      ? ""
      : (window.sessionStorage.getItem("lessonforge-token") ?? ""),
  );
  const login = (value: string) => {
    window.sessionStorage.setItem("lessonforge-token", value);
    setToken(value);
  };
  const logout = () => {
    window.sessionStorage.removeItem("lessonforge-token");
    queryClient.clear();
    setToken("");
  };

  if (!mounted) {
    return (
      <div className="app-loading">
        <LoadingState label="開啟 LessonForge 工作台…" />
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ScrollToTop />
        {token ? (
          <AuthenticatedApp
            token={token}
            logout={logout}
            onTokenChange={login}
          />
        ) : (
          <LoginPage onLogin={login} />
        )}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
