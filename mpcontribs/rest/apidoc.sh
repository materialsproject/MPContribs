#!/bin/bash

sed_cmd=sed
$sed_cmd --version > /dev/null 2>&1
if [ $? == 1 ]; then sed_cmd=gsed; fi
$sed_cmd --version > /dev/null 2>&1
if [ $? == 1 ]; then
  echo "gnu sed not found!"
  exit 1
fi
echo "using $sed_cmd"

apidoc -f "views.py" -f "_apidoc.py" -o static

for name in locales/locale main; do
  $sed_cmd --in-place "s:'./:'/static/:g" static/${name}.js
done

$sed_cmd --in-place 's:link href=":link href="/static/:g' static/index.html
$sed_cmd --in-place 's:script src=":script src="/static/:g' static/index.html
$sed_cmd --in-place \
  's:<script data-main="main.js" src="vendor/require.min.js"></script>:<script src="/static/vendor/require.min.js"></script><script src="/static/main.js"></script>:g' \
  static/index.html

$sed_cmd --in-place '1,3d' static/utils/send_sample_request.js
$sed_cmd --in-place '1 i\
  define(["jquery", "/static/jquery_cookie.js" ], function($, Cookies) {\
' static/utils/send_sample_request.js
$sed_cmd -in-place '92 i\
  var csrftoken = Cookies.get("csrftoken");\
  function csrfSafeMethod(method) {\
    // these HTTP methods do not require CSRF protection\
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));\
  }\
  $.ajaxSetup({\
    beforeSend: function(xhr, settings) {\
      if (!csrfSafeMethod(settings.type) && !this.crossDomain) {\
        xhr.setRequestHeader("X-CSRFToken", csrftoken);\
      }\
    }\
  });\
' static/utils/send_sample_request.js
