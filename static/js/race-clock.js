// The race clock on the race day page (slice 9): the site's time of day, and
// the time since the start, ticking every second.
//
// The page is served with the site's time. The difference between that and
// this device's clock is worked out once, so the clock shows the site's time -
// the time a tap on Finished records - even if the tablet's own clock is out.
// Without this script the page still works; the clock just doesn't tick.
// This is the project's one hand-written script; see docs/decisions.md.
(function () {
  var clock = document.getElementById("race-clock");
  if (!clock) return;
  var offset = Number(clock.dataset.now) - Date.now();
  var start = Number(clock.dataset.start);
  var timeOfDay = new Intl.DateTimeFormat("en-GB", {
    timeZone: clock.dataset.tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  });
  var shown = clock.querySelector(".clock-time");
  var elapsed = clock.querySelector(".clock-elapsed");

  function hms(ms) {
    var s = Math.floor(ms / 1000);
    var two = function (n) { return (n < 10 ? "0" : "") + n; };
    return Math.floor(s / 3600) + ":" + two(Math.floor(s / 60) % 60) + ":" + two(s % 60);
  }

  function tick() {
    var now = Date.now() + offset;
    shown.textContent = timeOfDay.format(now);
    elapsed.textContent = now < start ? "starts in " + hms(start - now + 999) : hms(now - start);
  }

  tick();
  setInterval(tick, 1000);
})();
