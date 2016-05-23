#!/bin/bash
apidoc -f "views.py" -f "_apidoc.py" -o static
for name in locales/locale main; do
  sed -e "s:\'\.\/:'/static/:g" -i '' static/${name}.js
done
sed -e 's:link href=":link href="/static/:g' -i '' static/index.html
sed -e 's:script src=":script src="/static/:g' -i '' static/index.html
sed -e \
  's:<script data-main="main.js" src="vendor/require.min.js"></script>:<script src="/static/vendor/require.min.js"></script><script src="/static/main.js"></script>:g' \
  -i '' static/index.html
sed -e '1,3d' -i '' static/utils/send_sample_request.js
sed -e '1 i\
  define(["jquery", "/static/jquery_cookie.js" ], function($, Cookies) {\
' -i '' static/utils/send_sample_request.js
sed -e '92 i\
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
' -i '' static/utils/send_sample_request.js
