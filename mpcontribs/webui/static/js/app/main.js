define(function(require) {
  var $ = require('jquery');
  require('bootstrap');
  require('filestyle');
  require('chosen');
  require('waitfor');
  var env = require('env');

  // make file upload button
  var upload_btn = $('#fileUpload');
  upload_btn.filestyle({
    iconName: "", input: false, badge: false,
    buttonName:"btn-info", buttonText:'<i class="fa fa-file-text" aria-hidden="true"></i>'
  });
  // replace text of upload button with selected file name
  upload_btn.change(function () {
    upload_btn.filestyle(
        'buttonText',
        '<i class="fa fa-file-text-o" aria-hidden="true"></i>'
        );
  });

  // select options in selectpicker based on session.options
  $.waitFor('#selectpicker').done(function(elements) {
    for (var i=0, iLen=env.options.length; i<iLen; i++) {
      $("#selectpicker [value=" + env.options[i] + "]").prop("selected",true);
    }
    $(elements[0]).chosen({
      search_contains: true, max_selected_options: 2, width: "350px",
      disable_search_threshold: 10
    });
    // on-change action for selectpicker
    $(elements[0]).on('change', function () {
      // - update options hidden input field with current selection
      // - en-/disable ArchieML sandbox and show/hide "Load MPFile"
      var options = [];
      for (var i=0, iLen=this.options.length; i<iLen; i++) {
        var opt = this.options[i];
        if (opt.selected) {
          options.push(opt.value);
          if (opt.parentNode.label == 'format') {
            if (opt.value != 'archieml') {
              $("#loadbutton").addClass('disabled');
              $(".sandbox").hide();
            } else {
              $("#loadbutton").removeClass('disabled');
              $(".sandbox").show();
            }
          }
          if (opt.parentNode.label == 'projects') {
              var aml = document.getElementById('inputaml_'+opt.value).value;
              var area = document.getElementsByTagName('textarea')[0];
              area.value = aml;
              area.dispatchEvent(new Event('keyup'));
          }
        }
      }
      document.getElementById('inputopts').value = JSON.stringify(options);
    });
  });

  // initialize hidden input field for options
  $.waitFor('#inputopts').done(function(elements) {
    elements[0].value = JSON.stringify(env.options);
  });
});
