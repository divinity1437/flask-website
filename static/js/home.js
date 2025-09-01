$(function() {
    /* NOTE: hard-refresh the browser once you've updated this */
    $(".typed").typed({
      strings: [
        "whoami<br/>" +
        "><span class='caret'>$</span> job: mobile network operator :o <br/> ^100" +
        "><span class='caret'>$</span> skills: html, css, python <br/> ^100" +
        "><span class='caret'>$</span> hobbies: coding python<br/> ^300"
      ],
      showCursor: true,
      cursorChar: '_',
      autoInsertCss: true,
      typeSpeed: 0.001,
      startDelay: 50,
      loop: false,
      showCursor: false,
      onStart: $('.message form').hide(),
      onStop: $('.message form').show(),
      onTypingResumed: $('.message form').hide(),
      onTypingPaused: $('.message form').show(),
      onComplete: $('.message form').show(),
      onStringTyped: function(pos, self) {$('.message form').show();},
    });
    $('.message form').hide()
  });
  console.log("skyloc was here :detective:")
  $(".theme-switch").on("click", () => {
    $("body").toggleClass("light-theme");
  });
