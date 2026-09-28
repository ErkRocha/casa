import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { ThemeProvider } from "@/components/theme-provider";
import { FilterProvider } from "@/features/filters/filter-context";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {/* Acima do roteamento: o filtro sobrevive à troca de tela. */}
        <FilterProvider>
          <App />
        </FilterProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
