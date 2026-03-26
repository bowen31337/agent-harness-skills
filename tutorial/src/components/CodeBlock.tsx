import { useEffect, useState } from "react";
import { type Highlighter, createHighlighter } from "shiki";

interface CodeBlockProps {
	code: string;
	lang: string;
	filename?: string;
}

let highlighterPromise: Promise<Highlighter> | null = null;

function getHighlighter() {
	if (!highlighterPromise) {
		highlighterPromise = createHighlighter({
			themes: ["vitesse-dark"],
			langs: ["typescript", "bash", "python", "yaml", "json", "tsx"],
		});
	}
	return highlighterPromise;
}

export default function CodeBlock({ code, lang, filename }: CodeBlockProps) {
	const [html, setHtml] = useState<string>("");
	const [copied, setCopied] = useState(false);

	useEffect(() => {
		getHighlighter().then((hl) => {
			const highlighted = hl.codeToHtml(code, { lang, theme: "vitesse-dark" });
			setHtml(highlighted.replace("<pre ", '<pre role="code" '));
		});
	}, [code, lang]);

	const handleCopy = () => {
		navigator.clipboard.writeText(code);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	return (
		<div className="bg-[#1e1e2e] rounded-lg border border-white/10 overflow-hidden">
			{filename && (
				<div className="flex items-center px-4 py-2 border-b border-white/10 bg-white/5">
					<span className="text-sm text-white/60 font-mono">{filename}</span>
				</div>
			)}
			<div className="relative">
				<button
					type="button"
					onClick={handleCopy}
					className="absolute top-2 right-2 px-2 py-1 text-xs text-white/50 hover:text-white/80 bg-white/10 hover:bg-white/20 rounded transition-colors"
				>
					{copied ? "Copied!" : "Copy"}
				</button>
				{html ? (
					<div
						className="overflow-x-auto [&_pre]:p-4 [&_pre]:m-0 [&_pre]:bg-transparent"
						dangerouslySetInnerHTML={{ __html: html }}
					/>
				) : (
					<pre
						role="code"
						className="p-4 m-0 text-sm font-mono text-white/80 overflow-x-auto bg-transparent"
					>
						{code}
					</pre>
				)}
			</div>
		</div>
	);
}
