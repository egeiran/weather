/**
 * Runs an async lookup for the newest input only. At most one call is in flight; inputs that
 * arrive meanwhile collapse to the latest, which runs as soon as the current call settles.
 * Every settled call is reported (so a drag shows values as it goes), except after `cancel()`.
 */
export class LatestOnly<I, O> {
  private busy = false;
  private next: { input: I } | null = null;
  private generation = 0;

  constructor(
    private readonly fn: (input: I) => Promise<O>,
    private readonly onResult: (input: I, output: O) => void,
    private readonly onError: (input: I, error: unknown) => void = () => {},
  ) {}

  push(input: I): void {
    this.next = { input };
    void this.pump();
  }

  /** Drop the pending input and ignore the result of the call in flight. */
  cancel(): void {
    this.next = null;
    this.generation++;
  }

  private async pump(): Promise<void> {
    if (this.busy || !this.next) return;
    const { input } = this.next;
    this.next = null;
    this.busy = true;
    const gen = this.generation;
    try {
      const out = await this.fn(input);
      if (gen === this.generation) this.onResult(input, out);
    } catch (err) {
      if (gen === this.generation) this.onError(input, err);
    } finally {
      this.busy = false;
    }
    await this.pump();
  }
}
