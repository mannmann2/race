"""Interact with the continent/source pickers as a user would."""
def select_sources(page,value):
 picker=page.locator('#source-picker')
 if picker.get_attribute('open') is None:picker.locator('summary').click()
 for checkbox in page.locator('input[name=sources]').all():
  if checkbox.is_checked():checkbox.uncheck()
 selected=['utmb','itra'] if value=='both' else value if isinstance(value,list) else [value] if value else []
 for source in selected:page.locator(f'input[name=sources][value="{source}"]').check()
 if value=='both':page.locator('#source-match-all').check()

def select_continents(page,values):
 picker=page.locator('#continent-picker')
 if picker.get_attribute('open') is None:picker.locator('summary').click()
 for checkbox in page.locator('input[name=continents]').all():
  if checkbox.is_checked():checkbox.uncheck()
 for continent in values:page.locator(f'input[name=continents][value="{continent}"]').check()
