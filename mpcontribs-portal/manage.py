#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys

if __name__ == "__main__":
    import django_settings_file

    django_settings_file.setup()

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
