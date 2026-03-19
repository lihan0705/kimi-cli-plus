import type { LiveMessage } from "@/hooks/types";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type TurnNavigatorProps = {
  messages: LiveMessage[];
  visible: boolean;
  onNavigateToTurn: (messageIndex: number) => void;
};

/**
 * Extract unique turns from messages.
 * Each turn starts with a user message.
 * Returns array of { turnIndex, messageIndex, content } for user messages.
 */
function extractTurns(messages: LiveMessage[]) {
  const turns: Array<{
    turnIndex: number;
    messageIndex: number;
    content: string;
  }> = [];

  messages.forEach((message, index) => {
    if (message.role === "user") {
      turns.push({
        turnIndex: message.turnIndex ?? turns.length,
        messageIndex: index,
        content: message.content ?? "",
      });
    }
  });

  return turns;
}

/**
 * Truncate text to a maximum length with ellipsis.
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "…";
}

export function TurnNavigator({
  messages,
  visible,
  onNavigateToTurn,
}: TurnNavigatorProps) {
  const turns = extractTurns(messages);

  // Don't render if there are fewer than 2 turns
  if (turns.length < 2) {
    return null;
  }

  return (
    <div
      className={cn(
        "fixed right-0 top-0 z-10 h-full py-16",
        "flex flex-col items-center justify-center gap-1",
        "transition-opacity duration-200",
        visible ? "opacity-100" : "opacity-0 pointer-events-none"
      )}
      role="navigation"
      aria-label="Conversation turns"
    >
      <div className="flex flex-col items-center gap-1 rounded-l-md bg-muted/50 px-1 py-2 backdrop-blur-sm">
        {turns.map((turn) => (
          <Tooltip key={turn.turnIndex}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => onNavigateToTurn(turn.messageIndex)}
                className={cn(
                  "size-2 rounded-full cursor-pointer",
                  "bg-muted-foreground/40 transition-all",
                  "hover:bg-foreground hover:size-3"
                )}
                aria-label={`Go to turn ${turn.turnIndex + 1}`}
              />
            </TooltipTrigger>
            <TooltipContent
              side="left"
              className="max-w-[280px] text-left break-words"
            >
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Turn {turn.turnIndex + 1}
              </p>
              <p>{truncateText(turn.content, 100)}</p>
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
