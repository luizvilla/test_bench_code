// Reusable multiple-choice quiz with immediate feedback.
// Usage: <div id="quiz"></div>
//        <script type="application/json" id="quiz-data">[{"q": "...", "options": ["..."], "answer": 0, "why": "html"}]</script>
//        <script src="../assets/quiz.js"></script>
(function () {
  const root = document.getElementById("quiz");
  const data = JSON.parse(document.getElementById("quiz-data").textContent);
  let answered = 0, right = 0;

  const score = document.createElement("div");
  score.className = "quiz-score";
  const label = document.createElement("span");
  const reset = document.createElement("button");
  reset.textContent = "Retry all";
  reset.onclick = () => location.reload();
  score.append(label, reset);

  function updateScore() {
    label.textContent = `${right} / ${answered} correct · ${data.length - answered} to go`;
  }

  data.forEach((item, i) => {
    const box = document.createElement("div");
    box.className = "quiz-q";
    const stem = document.createElement("div");
    stem.className = "stem";
    stem.innerHTML = `<span class="n">${i + 1}.</span>${item.q}`;
    box.append(stem);
    const why = document.createElement("div");
    why.className = "why";
    why.innerHTML = item.why;
    const buttons = item.options.map((text, j) => {
      const b = document.createElement("button");
      b.className = "opt";
      b.innerHTML = text;
      b.onclick = () => {
        buttons.forEach((x) => (x.disabled = true));
        buttons[item.answer].classList.add("right");
        if (j !== item.answer) b.classList.add("wrong"); else right++;
        why.insertAdjacentHTML("afterbegin", j === item.answer ? "<strong>Right.</strong> " : "<strong>Not quite.</strong> ");
        box.classList.add("answered");
        answered++;
        updateScore();
      };
      box.append(b);
      return b;
    });
    box.append(why);
    root.append(box);
  });
  root.after(score);
  updateScore();
})();
