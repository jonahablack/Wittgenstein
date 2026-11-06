import { Component, type ReactNode } from "react";

/** If a view fails while rendering, say so in place instead of leaving a blank page.
 *  `resetKey` clears the error when it changes (e.g. a new question is asked). */
export class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: unknown },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(prev: { resetKey?: unknown }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey)
      this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mt-6 rounded-xl border border-omit/40 bg-surface px-5 py-4 text-sm text-ink-2">
        Something on this page failed to display ({this.state.error.message}).
        Ask again, or reload the page.
      </div>
    );
  }
}
