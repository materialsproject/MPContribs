define(function(require) {
  var $ = require('jquery');
  require('chosen');

  $('.navbar-lower').affix({ offset: {top: -68} });
  $('#siteselect').chosen({ search_contains: true, disable_search_threshold: 10 });
  $('#dbselect').chosen({ search_contains: true, disable_search_threshold: 10 });

  // select options in siteselect and dbselect based on session.contribute
  $(document).ready(function(){
    var contrib_data = document.getElementById('input_contrib');
    var contrib = JSON.parse(contrib_data.value);
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
        $('#siteselect').trigger('chosen:updated');
      }
      $('#siteselect option[value="' + contrib['site'] + '"]').prop('selected', true);
    }
    $('#siteselect').trigger('chosen:updated');
    if ( 'dbtype' in contrib ) {
      $('#dbselect option[value="' + contrib['dbtype'] + '"]').prop('selected', true);
    }
    $('#dbselect').trigger('chosen:updated');
    if ( 'apikey' in contrib ) {
      document.getElementById('inputapikey').value = contrib['apikey'];
    }
    // on-change action for select option
    $('#siteselect').chosen().change(function () {
      document.getElementById('inputsite').value = this.value;
      var dlnk = document.getElementById('dlnk');
      dlnk.href = this.value + '/webtzite/dashboard';
    });
    $('#dbselect').chosen().change(function () {
      document.getElementById('inputdbtype').value = this.value;
    });
  });

});
