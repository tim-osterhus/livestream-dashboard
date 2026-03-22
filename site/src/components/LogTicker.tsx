import { React, useEffect, useRef } from '../react-global.js';

interface LogTickerProps {
  lines: string[];
}

function splitTimestamp(line: string): { timestamp: string | null; message: string } {
  const match = line.match(/^(\[[^\]]+\])\s?(.*)$/);
  if (!match) {
    return { timestamp: null, message: line };
  }

  return {
    timestamp: match[1],
    message: match[2],
  };
}

export function LogTicker({ lines }: LogTickerProps) {
  const listRef = useRef(null as HTMLDivElement | null);
  const visibleLines = lines.slice(-18);

  useEffect(() => {
    const listElement = listRef.current;
    if (!listElement) {
      return;
    }

    listElement.scrollTo({
      top: listElement.scrollHeight,
      behavior: 'smooth',
    });
  }, [lines]);

  return (
    <section className="log-ticker" aria-label="Recent logs">
      <div className="log-ticker__list" ref={listRef}>
        {visibleLines.map((line, index) => {
          const isRecent = index >= visibleLines.length - 2;
          const { timestamp, message } = splitTimestamp(line);
          return (
            <div key={`${index}-${line}`} className={`log-ticker__line ${isRecent ? 'log-ticker__line--recent' : ''}`} title={line}>
              {timestamp ? <span className="log-ticker__timestamp">{timestamp}</span> : null}
              <span className="log-ticker__message">{message}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
