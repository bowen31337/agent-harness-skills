import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const basename = "/agent-harness-skills";

const params = new URLSearchParams(window.location.search);
const redirectPath = params.get("p");
if (redirectPath) {
	window.history.replaceState(null, "", `${basename}/${redirectPath}`);
}

createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<BrowserRouter basename={basename}>
			<App />
		</BrowserRouter>
	</StrictMode>,
);
