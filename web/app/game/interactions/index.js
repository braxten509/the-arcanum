import { InteractionRegistry } from "./registry.js";
import { choiceInteraction } from "./choice.js";
import { copyInteraction } from "./copy.js";
import { runnableInteraction } from "./runnable.js";
import { fillInteraction, textInteraction } from "./text.js";

export const interactions = new InteractionRegistry()
  .register("mc", choiceInteraction)
  .register("multiple-choice", choiceInteraction)
  .register("fill", fillInteraction)
  .register("fill-code", fillInteraction)
  .register("text", textInteraction)
  .register("short-text", textInteraction)
  .register("trace-table", textInteraction)
  .register("type", copyInteraction)
  .register("copy-code", copyInteraction)
  .register("write", runnableInteraction)
  .register("runnable-code", runnableInteraction)
  .register("workspace-lab", runnableInteraction);
