export default function LoadingFallback() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center">
      <div className="animate-pulse">
        <span className="gradient-text text-xl font-semibold">Loading...</span>
      </div>
    </div>
  );
}
