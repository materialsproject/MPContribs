define(function(require) {
  var $ = require('jquery');
  require('chosen');
  require('waitfor');

  // select options in siteselect and dbselect based on session.contribute
  $.waitFor('#input_contrib').done(function(elements) {
    var contrib = JSON.parse(elements[0].value);
    if ( 'site' in contrib ) {
      var siteselect = document.getElementById('siteselect');
      for (var i=0, iLen=siteselect.options.length; i<iLen; i++) {
        site_in_opts = false;
        if (siteselect.options[i].value == contrib['site']) {
          site_in_opts = true; break;
        }
      }
      if (!site_in_opts) {
        var entry = document.createElement('option');
        entry.value = contrib['site'];
        entry.innerHTML = 'MP Dev'; // TODO use hidden input field and contrib['name']
        siteselect.appendChild(entry);
      }
      $('#siteselect option[value="' + contrib['site'] + '"]').prop('selected', true);
    }
    if ( 'dbtype' in contrib ) {
      $('#dbselect option[value="' + contrib['dbtype'] + '"]').prop('selected', true);
    }
    if ( 'apikey' in contrib ) {
      document.getElementById('inputapikey').value = contrib['apikey'];
    }

    $('#siteselect').chosen({
      search_contains: true, disable_search_threshold: 10, width: "180px"
    });
    $('#siteselect').chosen().change(function () {
      document.getElementById('inputsite').value = this.value;
      var dlnk = document.getElementById('dlnk');
      dlnk.href = this.value + '/dashboard';
    });
    //$('#add_site_btn').removeClass('hide');
    //$('#dbselect').chosen({
    //  search_contains: true, disable_search_threshold: 10, width: "150px"
    //});
    //$('#dbselect').chosen().change(function () {
    //  document.getElementById('inputdbtype').value = this.value;
    //});
    $('#inputapikey').removeClass('hide');
    $('#dlnk').show();
    $('#go_btn').removeClass('hide');
    $('#cancel_btn').removeClass('hide');

  });

});
