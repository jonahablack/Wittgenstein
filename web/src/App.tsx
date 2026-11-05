import { AnimatePresence, motion } from "motion/react";
import { Suspense, lazy, useEffect } from "react";
import { AnswerCard } from "./components/AnswerCard";
import { AskBar } from "./components/AskBar";
import { ChecksPanel } from "./components/Checks";
import { CompareView } from "./components/CompareView";
import { QueryAnatomy } from "./components/QueryAnatomy";
import { Receipt } from "./components/Receipt";
import { SourceDrawer } from "./components/SourceDrawer";
import { TopBar } from "./components/TopBar";
import { useRoute } from "./route";
import { useApp } from "./store";

// The process view (PixiJS evidence field, timeline, ledger) is code-split: the default
// answer view never downloads the rendering engine.
const ProcessView = lazy(() => import("./process/ProcessView"));
const ApiDocs = lazy(() => import("./about/ApiDocs").then((m) => ({ default: m.ApiDocs })));
const PipelineView = lazy(() => import("./about/PipelineView").then((m) => ({ default: m.PipelineView })));
const About = lazy(() => import("./about/About").then((m) => ({ default: m.About })));

export function App() {
  const init = useApp((s) => s.init);
  const run = useApp((s) => s.run);
  const loadError = useApp((s) => s.loadError);
  const showProcess = useApp((s) => s.showProcess);
  const compare = useApp((s) => s.compare);
  const active = useApp((s) => s.activePipeline);
  const route = useRoute();

  useEffect(() => {
    void init();
  }, [init]);

  const multi = !!run && run.order.length > 1 && compare;
  const pipeline = run && active ? run.pipelines[active] : undefined;

  return (
    <div className="bg-instrument min-h-full">
      <TopBar />
      <main className="mx-auto w-full max-w-[1180px] px-4 pb-24 sm:px-6">
        {route !== "app" ? (
          <Suspense fallback={<div className="mt-24 h-96 animate-pulse rounded-2xl border border-line bg-surface" />}>
            {route === "about" ? <About /> : route === "api" ? <ApiDocs /> : <PipelineView />}
          </Suspense>
        ) : loadError ? (
          <div className="mt-24 rounded-xl border border-omit/40 bg-surface p-6 text-ink-2">
            Couldn't reach the Wittgenstein engine: {loadError}. Start it with{" "}
            <code className="num text-ink">make live</code> in <code className="num">engine/</code>.
          </div>
        ) : (
          <>
            {/* The intro unmounts at once when a question is asked: an exit animation
                would hold its space and then make the whole page jump. */}
            {!run && (
                <motion.section
                  key="hero"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="pt-[14vh] pb-8 text-center"
                >
                  <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
                    Answers that show their work.
                  </h1>
                  <p className="mx-auto mt-4 max-w-2xl text-pretty text-ink-2">
                    Ask a question about a document. You get an answer with every claim traced to its source, and a
                    record of what the system searched, what it left out, and what it already checked for you.
                  </p>
                </motion.section>
            )}
            <motion.div layout="position" transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }} className={run ? "pt-6" : ""}>
              <AskBar />
            </motion.div>
            {run && (
              <div className="mt-6 space-y-5">
                {run.analysis && <QueryAnatomy analysis={run.analysis} />}
                {run.status === "error" && (
                  <div className="rounded-xl border border-omit/40 bg-surface px-5 py-4 text-sm text-ink-2">
                    {run.error}
                  </div>
                )}
                {multi ? (
                  <CompareView run={run} />
                ) : (
                  pipeline && (
                    <>
                      <AnswerCard run={run} pipeline={pipeline} />
                      <Receipt run={run} pipeline={pipeline} />
                      <ChecksPanel run={run} pipeline={pipeline} />
                    </>
                  )
                )}
                <AnimatePresence>
                  {showProcess && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25, ease: [0.2, 0.7, 0.2, 1] }}
                      className="overflow-hidden"
                    >
                      <Suspense
                        fallback={<div className="h-[520px] animate-pulse rounded-2xl border border-line bg-surface" />}
                      >
                        <ProcessView />
                      </Suspense>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </>
        )}
      </main>
      <SourceDrawer />
    </div>
  );
}
