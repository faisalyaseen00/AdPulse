import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import Layout from "./components/Layout";
import { LoadingBlock } from "./components/ui";
import Overview from "./pages/Overview";

const Ask = lazy(() => import("./pages/Ask"));
const Suggestions = lazy(() => import("./pages/Suggestions"));
const Wasted = lazy(() => import("./pages/Wasted"));
const Report = lazy(() => import("./pages/Report"));
const DataStatus = lazy(() => import("./pages/DataStatus"));
const Present = lazy(() => import("./pages/Present"));

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } },
});

const page = (el: React.ReactNode) => <Suspense fallback={<LoadingBlock />}>{el}</Suspense>;

createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="present" element={<Suspense fallback={<div className="fixed inset-0 bg-[#16181d]" />}><Present /></Suspense>} />
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="ask" element={page(<Ask />)} />
            <Route path="suggestions" element={page(<Suggestions />)} />
            <Route path="wasted" element={page(<Wasted />)} />
            <Route path="report" element={page(<Report />)} />
            <Route path="data" element={page(<DataStatus />)} />
            <Route path="*" element={<p className="text-muted">This page doesn't exist.</p>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
