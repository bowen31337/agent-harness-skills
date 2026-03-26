import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
	children: ReactNode;
}

interface State {
	hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
	constructor(props: Props) {
		super(props);
		this.state = { hasError: false };
	}

	static getDerivedStateFromError(): State {
		return { hasError: true };
	}

	componentDidCatch(error: Error, info: ErrorInfo) {
		console.error("ErrorBoundary caught:", error, info);
	}

	render() {
		if (this.state.hasError) {
			return (
				<div className="min-h-screen flex flex-col items-center justify-center bg-surface-raised text-white gap-4">
					<h1 className="text-2xl font-bold">Something went wrong</h1>
					<button
						type="button"
						className="px-4 py-2 rounded bg-brand-purple text-white hover:opacity-80 transition-opacity"
						onClick={() => this.setState({ hasError: false })}
					>
						Retry
					</button>
				</div>
			);
		}

		return this.props.children;
	}
}
