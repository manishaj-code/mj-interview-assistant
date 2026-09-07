function nextDelayMs(attempt) {
  const seq = [500, 1000, 2000, 5000];
  return seq[Math.min(attempt, seq.length - 1)];
}

module.exports = { nextDelayMs };
