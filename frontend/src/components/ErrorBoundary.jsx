import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface for local debugging — production swap to a real sink later.
    console.error("[ErrorBoundary]", error, info?.componentStack);
  }

  reset = () => {
    this.setState({ error: null });
    if (typeof this.props.onRetry === "function") {
      this.props.onRetry();
    }
  };

  render() {
    if (this.state.error) {
      const message =
        this.state.error?.message ||
        String(this.state.error) ||
        "Something went wrong.";
      return (
        <div className="min-h-[60vh] flex items-center justify-center px-6">
          <div className="card max-w-md text-center space-y-4">
            <div className="text-danger text-sm font-medium">
              {this.props.title || "Something broke"}
            </div>
            <div className="text-xs text-textmute font-mono break-words">
              {message}
            </div>
            <button className="btn btn-secondary text-xs" onClick={this.reset}>
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
