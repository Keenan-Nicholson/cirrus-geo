import logging
import click


# Inspired from https://github.com/click-contrib/click-log


class ClickFormatter(logging.Formatter):
    colors = {
        'error': {'fg': 'red'},
        'exception': {'fg': 'red'},
        'critical': {'fg': 'red'},
        'debug': {'fg': 'blue'},
        'warning': {'fg': 'yellow'},
    }

    def format(self, record):
        if not record.exc_info:
            level = record.levelname.lower()
            msg = record.getMessage()
            if level in self.colors:
                msg = click.style('{}'.format(msg), **self.colors[level])
            return msg
        return super().format(self, record)


class ClickHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = ClickFormatter()

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname.lower()
            click.echo(msg, err=True)
        except Exception:
            self.handleError(record)
