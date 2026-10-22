import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderOptions, render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/** Fresh QueryClient per test, no retries, so failures surface immediately. */
export function createTestQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  return (
    <QueryClientProvider client={client ?? createTestQueryClient()}>{children}</QueryClientProvider>
  );
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: ({ children }) => <Providers>{children}</Providers>, ...options });
}
