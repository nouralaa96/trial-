package actions;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;

public class BrowserActions { 
	
	     public static WebDriver driver  ; 
	
	public WebDriver initializeWebdriver( ) {  
		 try {
			 driver = new ChromeDriver() ;
			   return driver ; 
		} catch (Exception e) {
			// TODO: handle exception 
			  return null ;
		}
		  
	}
	
  
	        public void maximizeWindow() {  
	        	
	    	  driver.manage().window().maximize(); 
	       }  
	        
	        
	        public void closeDriver(){
	            driver.close();
	        }
}
